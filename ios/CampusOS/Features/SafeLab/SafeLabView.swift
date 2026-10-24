import Charts
import SwiftUI

/// SafeLab: live lab conditions from ESP32 sensor nodes, with alerts faculty acknowledge.
struct SafeLabView: View {
    @EnvironmentObject private var safeLab: SafeLabStore
    @EnvironmentObject private var auth: AuthManager
    @State private var showingSignIn = false

    var body: some View {
        content
            .navigationTitle("SafeLab")
            .task(id: auth.isSignedIn) {
                guard auth.isSignedIn else { return safeLab.reset() }
                await safeLab.poll()
            }
            .sheet(isPresented: $showingSignIn) {
                NavigationStack { SignInView(showsCancel: true) }
            }
    }

    @ViewBuilder
    private var content: some View {
        if !auth.isSignedIn {
            ContentUnavailableView {
                Label("Sign In for Lab Safety", systemImage: "shield.lefthalf.filled")
            } description: {
                Text("Live temperature, humidity and gas readings from lab sensors.")
            } actions: {
                Button("Sign In") { showingSignIn = true }
                    .buttonStyle(.borderedProminent)
            }
        } else if let dashboard = safeLab.dashboard {
            list(dashboard)
        } else if let message = safeLab.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load SafeLab", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await safeLab.refresh() } }
                    .buttonStyle(.borderedProminent)
            }
        } else {
            ProgressView("Connecting to lab sensors…")
        }
    }

    private func list(_ dashboard: SafetyDashboard) -> some View {
        List {
            Section {
                LiveStatusRow(lastUpdated: safeLab.lastUpdated, errorMessage: safeLab.loadState.errorMessage)
            }
            if dashboard.labs.isEmpty {
                Section {
                    Text("No lab sensors are reporting yet. Sensor nodes post to /api/v1/telemetry/; for a demo without hardware run `manage.py simulate_reading SENSOR-LAB002 --temp 24 --humidity 45 --gas 600`.")
                        .foregroundStyle(.secondary)
                }
            }
            ForEach(dashboard.labs) { lab in
                LabSafetySection(lab: lab, thresholds: dashboard.thresholds)
            }
            Section {
                EmptyView()
            } footer: {
                Text("These are low-cost demonstration sensors, not certified life-safety devices. Always follow lab safety procedures and the building's fire and gas alarms. Gas values are raw MQ-2 readings, not calibrated concentrations.")
            }
        }
        .animation(.default, value: dashboard)
        .refreshable { await safeLab.refresh() }
    }
}

private struct LabSafetySection: View {
    let lab: LabSafety
    let thresholds: SafetyThresholds
    @EnvironmentObject private var safeLab: SafeLabStore
    @EnvironmentObject private var auth: AuthManager
    @State private var errorMessage: String?

    var body: some View {
        Section {
            if let latest = lab.latest {
                HStack(spacing: 10) {
                    MetricTile(title: "Temperature", value: latest.temperatureC.map { String(format: "%.1f °C", $0) },
                               level: level(latest.temperatureC, thresholds.temperatureC))
                    MetricTile(title: "Humidity", value: latest.humidityPct.map { String(format: "%.0f %%", $0) },
                               level: level(latest.humidityPct, thresholds.humidityPct))
                    MetricTile(title: "Gas (raw)", value: latest.gasRaw.map(String.init),
                               level: level(latest.gasRaw.map(Double.init), thresholds.gasRaw))
                }
                .listRowInsets(EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 12))
                HStack {
                    Text("Updated \(latest.recordedAt.formatted(date: .omitted, time: .standard))")
                    if latest.simulated {
                        StatusBadge(text: "Simulated", color: .purple)
                    }
                    Spacer()
                    Text(lab.sensors.map(\.id).joined(separator: ", "))
                }
                .font(.caption).foregroundStyle(.secondary)
            }
            if lab.history.count > 1 {
                TrendChart(title: "Temperature °C", points: lab.history.compactMap { r in
                    r.temperatureC.map { (r.recordedAt, $0) } },
                           warning: thresholds.temperatureC["warning_above"],
                           danger: thresholds.temperatureC["danger_above"])
                TrendChart(title: "Gas sensor (raw)", points: lab.history.compactMap { r in
                    r.gasRaw.map { (r.recordedAt, Double($0)) } },
                           warning: thresholds.gasRaw["warning_above"],
                           danger: thresholds.gasRaw["danger_above"])
            }
            ForEach(lab.alerts) { alert in
                AlertRow(alert: alert, canAcknowledge: auth.currentUser?.role.isStaff == true,
                         isBusy: safeLab.acknowledgingID == alert.id) {
                    Task {
                        do {
                            try await safeLab.acknowledge(alert)
                        } catch {
                            errorMessage = error.localizedDescription
                        }
                    }
                }
            }
        } header: {
            HStack {
                Text(lab.labName)
                Spacer()
                StatusBadge(text: lab.status.label, color: lab.status.color)
            }
        }
        .alert("Couldn't Acknowledge", isPresented: Binding(
            get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(errorMessage ?? "")
        }
    }

    /// Colour for one value using the server's thresholds.
    private func level(_ value: Double?, _ limits: [String: Double]) -> SafetyLevel {
        guard let value else { return .other }
        if let danger = limits["danger_above"], value >= danger { return .danger }
        if let warning = limits["warning_above"], value >= warning { return .warning }
        if let low = limits["warning_below"], value <= low { return .warning }
        return .normal
    }
}

private struct MetricTile: View {
    let title: String
    let value: String?
    let level: SafetyLevel

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value ?? "—")
                .font(.title3.weight(.semibold).monospacedDigit())
                .foregroundStyle(level == .other ? .secondary : level.color)
                .minimumScaleFactor(0.7)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(level.color.opacity(level == .normal || level == .other ? 0.06 : 0.14),
                    in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}

private struct TrendChart: View {
    let title: String
    let points: [(Date, Double)]
    let warning: Double?
    let danger: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Chart {
                ForEach(Array(points.enumerated()), id: \.offset) { _, point in
                    LineMark(x: .value("Time", point.0), y: .value(title, point.1))
                        .interpolationMethod(.monotone)
                        .foregroundStyle(.indigo)
                }
                if let warning {
                    RuleMark(y: .value("Warning", warning))
                        .foregroundStyle(.orange.opacity(0.6))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                }
                if let danger {
                    RuleMark(y: .value("Danger", danger))
                        .foregroundStyle(.red.opacity(0.6))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                }
            }
            .chartXAxis(.hidden)
            .frame(height: 90)
        }
        .padding(.vertical, 4)
        .accessibilityLabel("\(title) trend, latest \(points.last.map { String(format: "%.1f", $0.1) } ?? "none")")
    }
}

private struct AlertRow: View {
    let alert: SafetyAlertItem
    let canAcknowledge: Bool
    let isBusy: Bool
    let acknowledge: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(alert.message, systemImage: alert.level == .danger ? "exclamationmark.octagon.fill"
                                                                      : "exclamationmark.triangle.fill")
                .foregroundStyle(alert.level.color)
                .font(.subheadline.weight(.semibold))
            Text(alert.clearedAt.map { "Back to normal since \($0.formatted(date: .omitted, time: .shortened)) · needs acknowledgement" }
                 ?? "Since \(alert.openedAt.formatted(date: .omitted, time: .shortened)) · still out of range")
                .font(.caption).foregroundStyle(.secondary)
            if canAcknowledge {
                if isBusy {
                    ProgressView()
                } else {
                    Button("Acknowledge", action: acknowledge)
                        .buttonStyle(.bordered)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

extension SafetyLevel {
    var color: Color {
        switch self {
        case .normal: return .green
        case .warning: return .orange
        case .danger: return .red
        case .offline, .other: return .gray
        }
    }
}
