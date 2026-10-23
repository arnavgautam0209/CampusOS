import Foundation
import Testing
@testable import CampusOS

final class FakeAttendanceService: AttendanceService {
    var liveResponses: [Result<AttendanceLive, Error>] = []
    var mineResponses: [Result<[MyAttendance], Error>] = []
    var sessionResult: Result<LiveSession, Error> = .failure(APIError.badResponse)
    private(set) var liveFetches = 0
    private(set) var mineFetches = 0
    private(set) var opened: [(classroomId: String, title: String)] = []
    private(set) var closedIDs: [Int] = []

    func fetchLive() async throws -> AttendanceLive {
        liveFetches += 1
        return try (liveResponses.count > 1 ? liveResponses.removeFirst() : liveResponses[0]).get()
    }

    func fetchMine() async throws -> [MyAttendance] {
        mineFetches += 1
        return try (mineResponses.count > 1 ? mineResponses.removeFirst() : mineResponses[0]).get()
    }

    func openSession(classroomId: String, title: String) async throws -> LiveSession {
        opened.append((classroomId, title))
        return try sessionResult.get()
    }

    func closeSession(id: Int) async throws -> LiveSession {
        closedIDs.append(id)
        return try sessionResult.get()
    }
}

private let t0 = Date(timeIntervalSince1970: 1_800_000_000)

private func scan(_ id: Int, _ result: ScanResult = .marked, student: String? = "Alice Rao") -> ReaderScan {
    ReaderScan(id: id, deviceId: "READER-ROOM-101", uid: "04A1B2C3", result: result, student: student,
               classroomId: "ROOM-101", createdAt: t0.addingTimeInterval(Double(id)))
}

private func live(scans: [ReaderScan], sessions: [LiveSession] = [],
                  classrooms: [LiveClassroom] = []) -> AttendanceLive {
    AttendanceLive(generatedAt: t0, openSessions: sessions, readers: [], recentScans: scans, classrooms: classrooms)
}

private func liveSession(_ id: Int, room: String = "ROOM-101") -> LiveSession {
    LiveSession(id: id, title: "Lecture \(id)", classroomId: room, classroomName: room, openedBy: "Priya Nair",
                openedAt: t0, closedAt: nil, records: [])
}

private func mine(_ id: Int) -> MyAttendance {
    MyAttendance(id: id, sessionId: id, session: "Lecture \(id)", classroomId: "ROOM-101",
                 classroomName: "Room 101", source: .card, markedAt: t0)
}

@MainActor
@Suite("AttendanceStore")
struct AttendanceStoreTests {
    private let service = FakeAttendanceService()

    private func makeStore() -> AttendanceStore {
        AttendanceStore(service: service, now: { t0 })
    }

    @Test func firstLiveLoadHighlightsNothing() async {
        service.liveResponses = [.success(live(scans: [scan(2), scan(1)]))]
        let store = makeStore()

        await store.refreshLive()

        #expect(store.live?.recentScans.count == 2)
        #expect(store.newScanIDs.isEmpty)
        #expect(store.loadState == .loaded)
        #expect(store.lastUpdated == t0)
    }

    @Test func newTapsAreHighlightedOnNextRefresh() async {
        service.liveResponses = [
            .success(live(scans: [scan(1)])),
            .success(live(scans: [scan(3, .unknownCard, student: nil), scan(2), scan(1)])),
            .success(live(scans: [scan(3, .unknownCard, student: nil), scan(2), scan(1)])),
        ]
        let store = makeStore()

        await store.refreshLive()
        await store.refreshLive()
        #expect(store.newScanIDs == [2, 3])

        await store.refreshLive()
        #expect(store.newScanIDs.isEmpty)
    }

    @Test func failedRefreshKeepsLastGoodData() async {
        service.liveResponses = [.success(live(scans: [scan(1)])), .failure(APIError.unreachable)]
        let store = makeStore()

        await store.refreshLive()
        await store.refreshLive()

        #expect(store.live?.recentScans.map(\.id) == [1])
        #expect(store.loadState == .failed(APIError.unreachable.localizedDescription))
        #expect(store.lastUpdated == t0)
    }

    @Test func firstLiveFailureShowsError() async {
        service.liveResponses = [.failure(APIError.invalid("You do not have permission to perform this action."))]
        let store = makeStore()

        await store.refreshLive()

        #expect(store.live == nil)
        #expect(store.loadState.errorMessage == "You do not have permission to perform this action.")
    }

    @Test func studentRecordsHighlightNewAttendance() async {
        service.mineResponses = [.success([mine(1)]), .success([mine(2), mine(1)])]
        let store = makeStore()

        await store.refreshMine()
        #expect(store.newRecordIDs.isEmpty)

        await store.refreshMine()
        #expect(store.myRecords.map(\.id) == [2, 1])
        #expect(store.newRecordIDs == [2])
    }

    @Test func emptyStudentRecordsStillCountAsLoaded() async {
        service.mineResponses = [.success([])]
        let store = makeStore()

        await store.refreshMine()

        #expect(store.myRecords.isEmpty)
        #expect(store.lastUpdated == t0)
        #expect(store.loadState == .loaded)
    }

    @Test func pollingRepeatsAndStopsWhenCancelled() async {
        service.mineResponses = [.success([])]
        let store = makeStore()

        let task = Task { await store.poll(staff: false, every: .milliseconds(20)) }
        try? await Task.sleep(for: .milliseconds(150))
        task.cancel()
        await task.value
        let fetchesAtStop = service.mineFetches

        #expect(fetchesAtStop >= 2)
        #expect(service.liveFetches == 0)
        try? await Task.sleep(for: .milliseconds(80))
        #expect(service.mineFetches == fetchesAtStop)
    }

    @Test func openSessionSendsTrimmedTitleAndRefreshes() async throws {
        service.liveResponses = [
            .success(live(scans: [], classrooms: [LiveClassroom(id: "ROOM-101", name: "Room 101", hasOpenSession: false)])),
            .success(live(scans: [], sessions: [liveSession(5)],
                          classrooms: [LiveClassroom(id: "ROOM-101", name: "Room 101", hasOpenSession: true)])),
        ]
        service.sessionResult = .success(liveSession(5))
        let store = makeStore()
        await store.refreshLive()
        #expect(store.classroomsAvailableToOpen.map(\.id) == ["ROOM-101"])

        try await store.openSession(classroomId: "ROOM-101", title: "  CS201 Lecture 6 \n")

        #expect(service.opened.map(\.title) == ["CS201 Lecture 6"])
        #expect(service.opened.map(\.classroomId) == ["ROOM-101"])
        #expect(service.liveFetches == 2)
        #expect(store.live?.openSessions.map(\.id) == [5])
        #expect(store.classroomsAvailableToOpen.isEmpty)
        #expect(!store.isChangingSession)
    }

    @Test func failedOpenSurfacesServerMessageWithoutRefreshing() async {
        service.liveResponses = [.success(live(scans: []))]
        service.sessionResult = .failure(APIError.conflict("Room 101 already has an open session: Lecture 5."))
        let store = makeStore()
        await store.refreshLive()

        await #expect(throws: APIError.conflict("Room 101 already has an open session: Lecture 5.")) {
            try await store.openSession(classroomId: "ROOM-101", title: "Lecture 6")
        }
        #expect(service.liveFetches == 1)
        #expect(!store.isChangingSession)
    }

    @Test func closeSessionCallsServerAndRefreshes() async throws {
        service.liveResponses = [.success(live(scans: [], sessions: [liveSession(5)])), .success(live(scans: []))]
        service.sessionResult = .success(liveSession(5))
        let store = makeStore()
        await store.refreshLive()

        try await store.closeSession(try #require(store.live?.openSessions.first))

        #expect(service.closedIDs == [5])
        #expect(store.live?.openSessions.isEmpty == true)
    }

    @Test func noClassroomsAvailableBeforeFirstLoad() {
        #expect(makeStore().classroomsAvailableToOpen.isEmpty)
    }

    @Test func resetClearsEverything() async {
        service.liveResponses = [.success(live(scans: [scan(1)]))]
        let store = makeStore()
        await store.refreshLive()

        store.reset()

        #expect(store.live == nil)
        #expect(store.lastUpdated == nil)
        #expect(store.loadState == .idle)
    }
}

@Suite("Attendance decoding")
struct AttendanceDecodingTests {
    @Test func decodesLiveDashboardFromServer() throws {
        // Shape produced by GET /api/v1/attendance/live/.
        let json = """
        {"generatedAt":"2026-10-24T09:01:30.120000+00:00",
         "openSessions":[{"id":1,"title":"CS201 Lecture 5","classroomId":"ROOM-101",
           "classroomName":"Lecture Room 101, Block A","openedBy":"Priya Nair",
           "openedAt":"2026-10-24T09:00:00+00:00",
           "records":[{"id":7,"student":"Alice Rao","studentUsername":"alice","source":"card",
                       "markedAt":"2026-10-24T09:01:28.013549+00:00","deviceId":"READER-ROOM-101"},
                      {"id":8,"student":"bob","studentUsername":"bob","source":"manual",
                       "markedAt":"2026-10-24T09:02:00+00:00","deviceId":null}]}],
         "readers":[{"id":"READER-ROOM-101","name":"Room 101 card reader","classroomId":"ROOM-101",
                     "isActive":true,"hasKey":true,"lastSeenAt":"2026-10-24T09:01:28+00:00"}],
         "recentScans":[{"id":12,"deviceId":"READER-ROOM-101","uid":"DEADBEEF","result":"unknown_card",
                         "student":null,"classroomId":"ROOM-101","createdAt":"2026-10-24T09:01:29+00:00"},
                        {"id":11,"deviceId":"READER-ROOM-101","uid":"04A1B2C3","result":"marked",
                         "student":"Alice Rao","classroomId":"ROOM-101","createdAt":"2026-10-24T09:01:28+00:00"}]}
        """
        let live = try JSONDecoder.campusOS.decode(AttendanceLive.self, from: Data(json.utf8))
        let session = try #require(live.openSessions.first)
        #expect(session.records.map(\.source) == [.card, .manual])
        #expect(session.records[1].deviceId == nil)
        #expect(live.readers.first?.hasKey == true)
        #expect(live.recentScans.map(\.result) == [.unknownCard, .marked])
        #expect(live.recentScans.first?.student == nil)
    }

    @Test func classroomsDecodeAndAreOptionalForOlderServers() throws {
        let current = """
        {"generatedAt":"2026-10-24T09:01:30+00:00","openSessions":[],"readers":[],"recentScans":[],
         "classrooms":[{"id":"ROOM-101","name":"Lecture Room 101, Block A","hasOpenSession":true}]}
        """
        let older = #"{"generatedAt":"2026-10-24T09:01:30+00:00","openSessions":[],"readers":[],"recentScans":[]}"#
        let decoded = try JSONDecoder.campusOS.decode(AttendanceLive.self, from: Data(current.utf8))
        #expect(decoded.classrooms.first?.hasOpenSession == true)
        #expect(try JSONDecoder.campusOS.decode(AttendanceLive.self, from: Data(older.utf8)).classrooms.isEmpty)
    }

    @Test func closedSessionDecodesClosedAt() throws {
        let json = """
        {"id":5,"title":"Lecture 5","classroomId":"ROOM-101","classroomName":"Room 101","openedBy":null,
         "openedAt":"2026-10-24T09:00:00+00:00","closedAt":"2026-10-24T10:00:00.5+00:00","records":[]}
        """
        let session = try JSONDecoder.campusOS.decode(LiveSession.self, from: Data(json.utf8))
        #expect(session.closedAt != nil)
        #expect(session.openedBy == nil)
    }

    @Test func unknownScanResultDecodesAsOther() throws {
        let json = """
        {"id":1,"deviceId":"R","uid":"04A1B2C3","result":"pending_verification","student":null,
         "classroomId":"ROOM-101","createdAt":"2026-10-24T09:01:29+00:00"}
        """
        #expect(try JSONDecoder.campusOS.decode(ReaderScan.self, from: Data(json.utf8)).result == .other)
    }

    @Test func decodesMyAttendance() throws {
        let json = """
        [{"id":3,"sessionId":2,"session":"Lecture 2","classroomId":"ROOM-101",
          "classroomName":"Lecture Room 101, Block A","source":"card","markedAt":"2026-10-24T09:01:28+00:00"}]
        """
        let records = try JSONDecoder.campusOS.decode([MyAttendance].self, from: Data(json.utf8))
        #expect(records.first?.session == "Lecture 2")
    }

    @Test func onlyStudentsAreNotStaff() {
        #expect(!CampusRole.student.isStaff)
        #expect(CampusRole.faculty.isStaff)
        #expect(CampusRole.administrator.isStaff)
    }
}
