import Foundation
import Testing
@testable import CampusOS

/// A real response from GET /api/v1/safelab/ (three readings, the last one with high gas).
let safeLabFixtureJSON = #"""
{
 "generatedAt": "2026-10-24T03:04:55.478776+00:00",
 "labs": [
  {
   "labId": "LAB002",
   "labName": "Electronics Lab",
   "status": "danger",
   "online": true,
   "sensors": [
    {
     "id": "SENSOR-LAB002",
     "name": "Electronics Lab sensor node",
     "lastSeenAt": null
    }
   ],
   "latest": {
    "temperatureC": 25.1,
    "humidityPct": 47.0,
    "gasRaw": 2650,
    "level": "danger",
    "simulated": false,
    "recordedAt": "2026-10-24T03:04:55.464065+00:00"
   },
   "history": [
    {
     "temperatureC": 24.0,
     "humidityPct": 45.0,
     "gasRaw": 520,
     "level": "normal",
     "simulated": false,
     "recordedAt": "2026-10-24T03:04:55.461958+00:00"
    },
    {
     "temperatureC": 24.4,
     "humidityPct": 46.0,
     "gasRaw": 560,
     "level": "normal",
     "simulated": false,
     "recordedAt": "2026-10-24T03:04:55.462888+00:00"
    },
    {
     "temperatureC": 25.1,
     "humidityPct": 47.0,
     "gasRaw": 2650,
     "level": "danger",
     "simulated": false,
     "recordedAt": "2026-10-24T03:04:55.464065+00:00"
    }
   ],
   "alerts": [
    {
     "id": 1,
     "kind": "gas",
     "level": "danger",
     "message": "Gas sensor 2650 raw (danger above 2500)",
     "value": 2650.0,
     "openedAt": "2026-10-24T03:04:55.464777+00:00",
     "lastSeenAt": "2026-10-24T03:04:55.464006+00:00",
     "clearedAt": null
    }
   ]
  }
 ],
 "thresholds": {
  "temperatureC": {
   "warning_above": 32.0,
   "danger_above": 40.0,
   "warning_below": 10.0
  },
  "humidityPct": {
   "warning_above": 80.0,
   "warning_below": 15.0
  },
  "gasRaw": {
   "warning_above": 1500,
   "danger_above": 2500
  }
 }
}
"""#

func safeLabFixture() throws -> SafetyDashboard {
    try JSONDecoder.campusOS.decode(SafetyDashboard.self, from: Data(safeLabFixtureJSON.utf8))
}

final class FakeSafeLabService: SafeLabService {
    var results: [Result<SafetyDashboard, Error>] = []
    var acknowledgeError: Error?
    private(set) var fetches = 0
    private(set) var acknowledged: [Int] = []

    func fetchDashboard() async throws -> SafetyDashboard {
        fetches += 1
        return try (results.count > 1 ? results.removeFirst() : results[0]).get()
    }

    func acknowledge(alertID: Int) async throws {
        acknowledged.append(alertID)
        if let acknowledgeError { throw acknowledgeError }
    }
}

@Suite("SafeLab decoding")
struct SafeLabDecodingTests {
    @Test func decodesRealDashboard() throws {
        let dashboard = try safeLabFixture()
        let lab = try #require(dashboard.labs.first)
        #expect(lab.labName == "Electronics Lab")
        #expect(lab.status == .danger)
        #expect(lab.online)
        #expect(lab.history.compactMap(\.gasRaw) == [520, 560, 2650])   // oldest first
        #expect(lab.latest?.gasRaw == 2650)
        #expect(lab.latest?.simulated == false)
        #expect(lab.sensors.first?.id == "SENSOR-LAB002")
        let alert = try #require(lab.alerts.first)
        #expect((alert.kind, alert.level, alert.value) == ("gas", .danger, 2650))
        #expect(alert.clearedAt == nil)
        #expect(dashboard.thresholds.gasRaw["danger_above"] == 2500)
        #expect(dashboard.thresholds.temperatureC["warning_below"] == 10)
    }

    @Test func unknownLevelDecodesAsOther() throws {
        #expect(try JSONDecoder.campusOS.decode([SafetyLevel].self, from: Data(#"["evacuate"]"#.utf8)) == [.other])
    }
}

@MainActor
@Suite("SafeLabStore")
struct SafeLabStoreTests {
    private let service = FakeSafeLabService()
    private let t0 = Date(timeIntervalSince1970: 1_800_000_000)

    @Test func refreshLoadsDashboard() async throws {
        service.results = [.success(try safeLabFixture())]
        let fixedNow = t0
        let store = SafeLabStore(service: service, now: { fixedNow })
        await store.refresh()
        #expect(store.dashboard?.labs.count == 1)
        #expect(store.lastUpdated == t0)
        #expect(store.loadState == .loaded)
    }

    @Test func failedRefreshKeepsLastReadings() async throws {
        service.results = [.success(try safeLabFixture()), .failure(APIError.unreachable)]
        let store = SafeLabStore(service: service)
        await store.refresh()
        await store.refresh()
        #expect(store.dashboard != nil)
        #expect(store.loadState.errorMessage == APIError.unreachable.localizedDescription)
    }

    @Test func acknowledgeCallsServerThenRefreshes() async throws {
        service.results = [.success(try safeLabFixture())]
        let store = SafeLabStore(service: service)
        await store.refresh()
        let alert = try #require(store.dashboard?.labs.first?.alerts.first)

        try await store.acknowledge(alert)

        #expect(service.acknowledged == [alert.id])
        #expect(service.fetches == 2)
        #expect(store.acknowledgingID == nil)
    }

    @Test func refusedAcknowledgeSurfacesError() async throws {
        service.results = [.success(try safeLabFixture())]
        service.acknowledgeError = APIError.invalid("Only faculty can acknowledge safety alerts.")
        let store = SafeLabStore(service: service)
        await store.refresh()
        let alert = try #require(store.dashboard?.labs.first?.alerts.first)

        await #expect(throws: APIError.invalid("Only faculty can acknowledge safety alerts.")) {
            try await store.acknowledge(alert)
        }
        #expect(service.fetches == 1)
        #expect(store.acknowledgingID == nil)
    }

    @Test func pollingStopsWhenCancelled() async throws {
        service.results = [.success(try safeLabFixture())]
        let store = SafeLabStore(service: service)
        let task = Task { await store.poll(every: .milliseconds(20)) }
        try? await Task.sleep(for: .milliseconds(150))
        task.cancel()
        await task.value
        let fetches = service.fetches
        #expect(fetches >= 2)
        try? await Task.sleep(for: .milliseconds(80))
        #expect(service.fetches == fetches)
    }

    @Test func resetClears() async throws {
        service.results = [.success(try safeLabFixture())]
        let store = SafeLabStore(service: service)
        await store.refresh()
        store.reset()
        #expect(store.dashboard == nil)
        #expect(store.loadState == .idle)
    }
}
