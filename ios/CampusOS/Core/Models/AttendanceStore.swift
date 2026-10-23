import Foundation
import Combine

/// Live attendance for ProxyGuard. Polls the server while a screen is open so
/// card taps on a reader show up in the app within a few seconds.
@MainActor
final class AttendanceStore: ObservableObject {
    @Published private(set) var live: AttendanceLive?
    @Published private(set) var myRecords: [MyAttendance] = []
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var lastUpdated: Date?
    /// Items that arrived in the latest refresh, so the UI can highlight them.
    @Published private(set) var newScanIDs: Set<Int> = []
    @Published private(set) var newRecordIDs: Set<Int> = []

    nonisolated static let pollInterval: Duration = .seconds(3)

    private let service: AttendanceService
    private let now: () -> Date
    private var hasLoadedMine = false

    init(service: AttendanceService, now: @escaping () -> Date = Date.init) {
        self.service = service
        self.now = now
    }

    func refreshLive() async {
        if live == nil { loadState = .loading }
        do {
            let next = try await service.fetchLive()
            // Nothing is "new" on the first load, only taps that arrive while watching.
            newScanIDs = live.map { Set(next.recentScans.map(\.id)).subtracting($0.recentScans.map(\.id)) } ?? []
            live = next
            lastUpdated = now()
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
            newRecordIDs = hasLoadedMine ? Set(next.map(\.id)).subtracting(myRecords.map(\.id)) : []
            myRecords = next
            hasLoadedMine = true
            lastUpdated = now()
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
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
        lastUpdated = nil
        loadState = .idle
    }
}
