import Charts
import SwiftUI

/// SafeLab: faults in physical lab equipment only. Students report and track; faculty review and see analytics.
struct SafeLabView: View {
    @EnvironmentObject private var faults: EquipmentFaultStore
    @EnvironmentObject private var auth: AuthManager
    @State private var showingSignIn = false
    @State private var page = Page.reports

    enum Page { case reports, analytics }

    private var isStaff: Bool { auth.currentUser?.role.isStaff == true }

    var body: some View {
        content
            .navigationTitle("SafeLab")
            .task(id: "\(auth.isSignedIn)-\(isStaff)") {
                guard auth.isSignedIn else { return faults.reset() }
                await faults.load(staff: isStaff)
            }
            .refreshable { await faults.load(staff: isStaff) }
            .sheet(isPresented: $showingSignIn) { NavigationStack { SignInView(showsCancel: true) } }
    }

    @ViewBuilder
    private var content: some View {
        if !auth.isSignedIn {
            ContentUnavailableView {
                Label("Sign In to Report Faults", systemImage: "wrench.and.screwdriver")
            } description: {
                Text("Report a fault in lab equipment and follow it until it's fixed.")
            } actions: {
                Button("Sign In") { showingSignIn = true }.buttonStyle(.borderedProminent)
            }
        } else if faults.labs.isEmpty, let message = faults.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load SafeLab", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await faults.load(staff: isStaff) } }.buttonStyle(.borderedProminent)
            }
        } else if faults.labs.isEmpty {
            ProgressView("Loading equipment…")
        } else {
            List {
                if isStaff {
                    Picker("View", selection: $page) {
                        Text("Reports").tag(Page.reports)
                        Text("Analytics").tag(Page.analytics)
                    }
                    .pickerStyle(.segmented)
                    .listRowBackground(Color.clear)
                }
                if isStaff && page == .analytics {
                    AnalyticsSections(analytics: faults.analytics)
                } else {
                    Section {
                        NavigationLink {
                            ReportFaultView()
                        } label: {
                            Label("Report an Equipment Fault", systemImage: "exclamationmark.triangle.fill")
                                .font(.headline)
                        }
                    } footer: {
                        Text("Only for faults in lab equipment: choose the lab, then the item.")
                    }
                    if isStaff {
                        FacultyReportSections()
                    } else {
                        Section("My Reports") {
                            if faults.reports.isEmpty {
                                Text("You haven't reported any faults.").foregroundStyle(.secondary)
                            }
                            ForEach(faults.reports) { FaultRow(report: $0, showsReporter: false) }
                        }
                    }
                }
            }
        }
    }
}

/// Lab → that lab's equipment → category, severity, description.
struct ReportFaultView: View {
    @EnvironmentObject private var faults: EquipmentFaultStore
    @Environment(\.dismiss) private var dismiss
    @State private var labId: String?
    @State private var equipment: FaultEquipment?
    @State private var category: FaultCategory?
    @State private var severity = FaultSeverity.medium
    @State private var description = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var submitted = false

    private var canSubmit: Bool {
        labId != nil && equipment != nil && category != nil
            && description.trimmingCharacters(in: .whitespacesAndNewlines).count >= 5 && !isSubmitting
    }

    var body: some View {
        Form {
            Section("1. Laboratory") {
                Picker("Laboratory", selection: $labId) {
                    Text("Choose a lab").tag(String?.none)
                    ForEach(faults.labs) { Text($0.name).tag(String?.some($0.id)) }
                }
            }
            Section("2. Equipment") {
                Picker("Equipment", selection: $equipment) {
                    Text(labId == nil ? "Choose a lab first" : "Choose an item").tag(FaultEquipment?.none)
                    ForEach(faults.equipment(inLab: labId)) { item in
                        Text("\(item.name) · \(item.id)").tag(FaultEquipment?.some(item))
                    }
                }
                .disabled(labId == nil)
                if let equipment {
                    LabeledContent("Asset ID", value: equipment.id)
                    LabeledContent("Type", value: equipment.type)
                }
            }
            Section("3. Fault") {
                Picker("Category", selection: $category) {
                    Text("Choose a category").tag(FaultCategory?.none)
                    ForEach(FaultCategory.allCases) { Text($0.label).tag(FaultCategory?.some($0)) }
                }
                Picker("Severity", selection: $severity) {
                    ForEach(FaultSeverity.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                TextField("Describe what's wrong with it", text: $description, axis: .vertical)
                    .lineLimit(3...6)
            }
            if let errorMessage {
                Section { Label(errorMessage, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red) }
            }
            Section {
                Button {
                    Task { await submit() }
                } label: {
                    HStack {
                        Spacer()
                        if isSubmitting { ProgressView() } else { Text("Submit Report").font(.headline) }
                        Spacer()
                    }
                }
                .disabled(!canSubmit)
            }
        }
        .navigationTitle("Report a Fault")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: labId) { _, _ in equipment = nil }   // equipment must come from the chosen lab
        .alert("Report Submitted", isPresented: $submitted) {
            Button("OK") { dismiss() }
        } message: {
            Text("Faculty will review it. Follow its status under My Reports.")
        }
    }

    private func submit() async {
        guard let labId, let equipment, let category else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        errorMessage = nil
        do {
            try await faults.submit(labId: labId, equipment: equipment, category: category, severity: severity,
                                    description: description)
            submitted = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct FacultyReportSections: View {
    @EnvironmentObject private var faults: EquipmentFaultStore
    @State private var rejecting: EquipmentFaultReport?
    @State private var reason = ""
    @State private var errorMessage: String?

    private let groups: [(String, [EquipmentFaultReport.Status])] = [
        ("Pending Review", [.pending]), ("In Progress", [.approved, .underMaintenance]),
        ("Closed", [.resolved, .rejected]),
    ]

    var body: some View {
        ForEach(groups, id: \.0) { title, statuses in
            let reports = faults.reports.filter { statuses.contains($0.status) }
            Section("\(title) (\(reports.count))") {
                if reports.isEmpty {
                    Text("None.").foregroundStyle(.secondary)
                }
                ForEach(reports) { report in
                    VStack(alignment: .leading, spacing: 8) {
                        FaultRow(report: report, showsReporter: true)
                        if faults.busyID == report.id {
                            ProgressView()
                        } else if !report.status.actions.isEmpty {
                            HStack(spacing: 8) {
                                ForEach(report.status.actions, id: \.rawValue) { action in
                                    button(action, report)
                                }
                            }
                            .font(.caption)
                            .disabled(faults.busyID != nil)
                        }
                    }
                }
            }
        }
        .alert("Reject Report", isPresented: Binding(get: { rejecting != nil }, set: { if !$0 { rejecting = nil } }),
               presenting: rejecting) { report in
            TextField("Reason (required)", text: $reason)
            Button("Reject", role: .destructive) {
                let note = reason
                Task { await act { try await faults.decide(report, .reject, note: note) } }
            }
            .disabled(reason.trimmingCharacters(in: .whitespaces).isEmpty)
            Button("Cancel", role: .cancel) {}
        } message: { report in
            Text("\(report.reporter) will see the reason on their report for \(report.equipmentName).")
        }
        .alert("Couldn't Update Report", isPresented: Binding(
            get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(errorMessage ?? "")
        }
    }

    @ViewBuilder
    private func button(_ action: FaultAction, _ report: EquipmentFaultReport) -> some View {
        switch action {
        case .reject:
            Button("Reject", role: .destructive) {
                reason = ""
                rejecting = report
            }
            .buttonStyle(.bordered)
        case .approve, .resolve:
            Button(action.label) { Task { await act { try await faults.decide(report, action) } } }
                .buttonStyle(.borderedProminent).tint(action == .approve ? .green : .teal)
        case .maintenance:
            Button(action.label) { Task { await act { try await faults.decide(report, action) } } }
                .buttonStyle(.bordered).tint(.orange)
        }
    }

    private func act(_ action: () async throws -> Void) async {
        do {
            try await action()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct FaultRow: View {
    let report: EquipmentFaultReport
    let showsReporter: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(report.equipmentName).font(.headline)
                    Text("\(report.labName) · \(report.equipmentId)").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                StatusBadge(text: report.status.label, color: statusColor)
            }
            Text("\(report.categoryLabel) · \(report.severity.capitalized) severity")
                .font(.subheadline.weight(.semibold)).foregroundStyle(severityColor)
            Text(report.description).font(.subheadline)
            Text((showsReporter ? "\(report.reporter) · " : "")
                 + report.createdAt.formatted(date: .abbreviated, time: .shortened))
                .font(.caption).foregroundStyle(.secondary)
            if !report.decisionNote.isEmpty {
                Text("\(report.decidedBy ?? "Faculty"): “\(report.decisionNote)”").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    private var statusColor: Color {
        switch report.status {
        case .pending: return .orange
        case .approved: return .blue
        case .underMaintenance: return .purple
        case .resolved: return .green
        case .rejected: return .red
        case .other: return .secondary
        }
    }

    private var severityColor: Color {
        switch report.severity {
        case "critical": return .red
        case "high": return .orange
        default: return .secondary
        }
    }
}

/// Equipment-only charts; every number comes from the server.
private struct AnalyticsSections: View {
    let analytics: FaultAnalytics?

    var body: some View {
        if let analytics {
            Section {
                Text("\(analytics.total) equipment fault reports").font(.headline)
            }
            chart("Monthly Fault Reports", analytics.monthly, color: .indigo, horizontal: false)
            chart("Reports by Status", analytics.byStatus, color: .teal, horizontal: true)
            chart("Faults by Laboratory", analytics.byLab, color: .orange, horizontal: true)
            chart("Faults by Equipment Type", analytics.byEquipmentType, color: .purple, horizontal: true)
            chart("Most Frequently Reported Equipment", analytics.mostReported, color: .red, horizontal: true)
        } else {
            Section { ProgressView() }
        }
    }

    private func chart(_ title: String, _ buckets: [FaultBucket], color: Color, horizontal: Bool) -> some View {
        Section(title) {
            if buckets.isEmpty {
                Text("No reports yet.").foregroundStyle(.secondary)
            } else if horizontal {
                Chart(buckets) { bucket in
                    BarMark(x: .value("Reports", bucket.count), y: .value("Item", bucket.label))
                        .foregroundStyle(color)
                        .annotation(position: .trailing) { Text("\(bucket.count)").font(.caption2) }
                }
                .frame(height: CGFloat(max(buckets.count, 2)) * 32)
            } else {
                Chart(buckets) { bucket in
                    BarMark(x: .value("Month", bucket.label), y: .value("Reports", bucket.count))
                        .foregroundStyle(color)
                        .annotation(position: .top) { Text("\(bucket.count)").font(.caption2) }
                }
                .frame(height: 180)
            }
        }
    }
}
