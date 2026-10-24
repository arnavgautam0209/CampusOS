import Foundation
import Combine

/// GET /api/v1/safelab/: live conditions for every lab with a sensor node.
struct SafetyDashboard: Codable, Equatable {
    let generatedAt: Date
    let labs: [LabSafety]
    let thresholds: SafetyThresholds
}

/// Demo thresholds from the server, e.g. temperatureC["danger_above"].
struct SafetyThresholds: Codable, Equatable {
    let temperatureC: [String: Double]
    let humidityPct: [String: Double]
    let gasRaw: [String: Double]
}

enum SafetyLevel: String, Codable {
    case normal, warning, danger, offline, other

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = SafetyLevel(rawValue: raw) ?? .other
    }

    var label: String {
        switch self {
        case .normal: return "Normal"
        case .warning: return "Warning"
        case .danger: return "Danger"
        case .offline: return "Sensor offline"
        case .other: return "Unknown"
        }
    }
}

struct LabSafety: Codable, Identifiable, Equatable {
    let labId: String
    let labName: String
    /// Latest level, "offline" without recent readings, raised to any un-acknowledged alert.
    let status: SafetyLevel
    let online: Bool
    let sensors: [SafetySensor]
    let latest: SafetyReading?
    /// Oldest first, for charts.
    let history: [SafetyReading]
    let alerts: [SafetyAlertItem]

    var id: String { labId }
}

struct SafetySensor: Codable, Equatable {
    let id: String
    let name: String
    let lastSeenAt: Date?
}

struct SafetyReading: Codable, Equatable {
    let temperatureC: Double?
    let humidityPct: Double?
    /// MQ-2 raw ADC value (0–4095), uncalibrated.
    let gasRaw: Int?
    let level: SafetyLevel
    /// Recorded with `manage.py simulate_reading` for a demo, not measured.
    let simulated: Bool
    let recordedAt: Date
}

struct SafetyAlertItem: Codable, Identifiable, Equatable {
    let id: Int
    let kind: String
    let level: SafetyLevel
    let message: String
    let value: Double
    let openedAt: Date
    let lastSeenAt: Date
    /// When readings went back to normal; the alert still waits for faculty.
    let clearedAt: Date?
}

protocol SafeLabService {
    func fetchDashboard() async throws -> SafetyDashboard
    func acknowledge(alertID: Int) async throws
}

struct APISafeLabService: SafeLabService {
    let api: APIClient

    func fetchDashboard() async throws -> SafetyDashboard {
        try await api.get("safelab/", authenticated: true)
    }

    func acknowledge(alertID: Int) async throws {
        struct Acknowledged: Decodable { let id: Int }
        let _: Acknowledged = try await api.post("safelab/alerts/\(alertID)/acknowledge/", authenticated: true)
    }
}

/// SafeLab: polls the server while the screen is open. Display only; the
/// sensor nodes run their own local alarms and the labs keep real alarms.
@MainActor
final class SafeLabStore: ObservableObject {
    @Published private(set) var dashboard: SafetyDashboard?
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var lastUpdated: Date?
    @Published private(set) var acknowledgingID: Int?

    nonisolated static let pollInterval: Duration = .seconds(5)

    private let service: SafeLabService
    private let now: () -> Date

    init(service: SafeLabService, now: @escaping () -> Date = Date.init) {
        self.service = service
        self.now = now
    }

    func refresh() async {
        if dashboard == nil { loadState = .loading }
        do {
            dashboard = try await service.fetchDashboard()
            lastUpdated = now()
            loadState = .loaded
        } catch {
            // Keep the last readings visible; the screen shows "Reconnecting".
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Refreshes until the calling task is cancelled (when the screen closes).
    func poll(every interval: Duration = SafeLabStore.pollInterval) async {
        while !Task.isCancelled {
            await refresh()
            try? await Task.sleep(for: interval)
        }
    }

    /// Faculty only (enforced by the server).
    func acknowledge(_ alert: SafetyAlertItem) async throws {
        acknowledgingID = alert.id
        defer { acknowledgingID = nil }
        try await service.acknowledge(alertID: alert.id)
        await refresh()
    }

    func reset() {
        dashboard = nil
        lastUpdated = nil
        loadState = .idle
    }
}
