import Foundation
import Combine

/// Live attendance for ProxyGuard. Polls the server every second while a screen
/// is open so a card tap on a reader shows up in the app almost at once.
@MainActor
final class AttendanceStore: ObservableObject {
    @Published private(set) var live: AttendanceLive?
    @Published private(set) var myRecords: [MyAttendance] = []
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var lastUpdated: Date?
    /// Items that arrived in the last few seconds (not on the first load), so the UI can highlight them.
    @Published private(set) var newScanIDs: Set<Int> = []
    @Published private(set) var newRecordIDs: Set<Int> = []
    /// Students marked present in an open session in the last few seconds (SessionAttendee ids).
    @Published private(set) var newAttendeeIDs: Set<Int> = []
    /// True while an open/close request is in flight, to disable the buttons.
    @Published private(set) var isChangingSession = false

    nonisolated static let pollInterval: Duration = .seconds(1)
    /// How long a new tap stays highlighted; longer than the poll interval so it doesn't just flash.
    nonisolated static let highlightDuration: TimeInterval = 8

    private let service: AttendanceService
    private let now: () -> Date
    private var hasLoadedMine = false
    private var scansSeen = RecentArrivals<Int>()
    private var attendeesSeen = RecentArrivals<Int>()
    private var recordsSeen = RecentArrivals<Int>()

    init(service: AttendanceService, now: @escaping () -> Date = Date.init) {
        self.service = service
        self.now = now
    }

    func refreshLive() async {
        if live == nil { loadState = .loading }
        do {
            let next = try await service.fetchLive()
            let time = now()
            // Nothing is "new" on the first load, only taps that arrive while watching.
            let firstLoad = live == nil
            newScanIDs = scansSeen.update(next.recentScans.map(\.id), firstLoad: firstLoad, now: time)
            newAttendeeIDs = attendeesSeen.update(next.openSessions.flatMap(\.records).map(\.id),
                                                  firstLoad: firstLoad, now: time)
            live = next
            lastUpdated = time
            loadState = .loaded
        } catch {
            // Keep showing the last good data; the UI shows a "reconnecting" banner.
            loadState = .failed(error.localizedDescription)
        }
    }

    func refreshMine() async {
        if !hasLoadedMine { loadState = .loading }
        do {
            let next = try await service.fetchMine()
            let time = now()
            newRecordIDs = recordsSeen.update(next.map(\.id), firstLoad: !hasLoadedMine, now: time)
            myRecords = next
            hasLoadedMine = true
            lastUpdated = time
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Rooms without an open session, for the Open Session picker.
    var classroomsAvailableToOpen: [LiveClassroom] {
        live?.classrooms.filter { !$0.hasOpenSession } ?? []
    }

    /// Faculty only (enforced by the server). Refreshes so the new session shows at once.
    func openSession(classroomId: String, title: String) async throws {
        isChangingSession = true
        defer { isChangingSession = false }
        _ = try await service.openSession(classroomId: classroomId,
                                          title: title.trimmingCharacters(in: .whitespacesAndNewlines))
        await refreshLive()
    }

    func closeSession(_ session: LiveSession) async throws {
        isChangingSession = true
        defer { isChangingSession = false }
        _ = try await service.closeSession(id: session.id)
        await refreshLive()
    }

    /// Refreshes until the calling task is cancelled (SwiftUI cancels `.task` when the screen closes).
    func poll(staff: Bool, every interval: Duration = AttendanceStore.pollInterval) async {
        while !Task.isCancelled {
            if staff { await refreshLive() } else { await refreshMine() }
            try? await Task.sleep(for: interval)
        }
    }

    func reset() {
        live = nil
        myRecords = []
        hasLoadedMine = false
        newScanIDs = []
        newRecordIDs = []
        newAttendeeIDs = []
        scansSeen = RecentArrivals<Int>()
        attendeesSeen = RecentArrivals<Int>()
        recordsSeen = RecentArrivals<Int>()
        lastUpdated = nil
        loadState = .idle
    }
}

/// Remembers when each id first appeared so the UI can highlight arrivals for a few seconds.
struct RecentArrivals<ID: Hashable> {
    private var known: Set<ID> = []
    private var firstSeen: [ID: Date] = [:]

    /// Returns the ids that first appeared within `duration` of `now`. On the first load everything
    /// is already there, so nothing counts as new.
    mutating func update(_ ids: [ID], firstLoad: Bool, now: Date,
                         duration: TimeInterval = AttendanceStore.highlightDuration) -> Set<ID> {
        let current = Set(ids)
        if !firstLoad {
            for id in current.subtracting(known) { firstSeen[id] = now }
        }
        known = current
        firstSeen = firstSeen.filter { current.contains($0.key) && now.timeIntervalSince($0.value) < duration }
        return Set(firstSeen.keys)
    }
}
