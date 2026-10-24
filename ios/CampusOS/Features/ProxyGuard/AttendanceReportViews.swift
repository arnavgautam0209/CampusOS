import QuickLook
import SwiftUI

/// Faculty: every recent session, open or closed, to pick one for its report.
struct AttendanceSessionsView: View {
    @EnvironmentObject private var reports: AttendanceReportStore

    var body: some View {
        Group {
            if reports.sessions.isEmpty, let message = reports.sessionsState.errorMessage {
                ContentUnavailableView {
                    Label("Can't Load Sessions", systemImage: "wifi.exclamationmark")
                } description: {
                    Text(message)
                } actions: {
                    Button("Try Again") { Task { await reports.loadSessions() } }
                        .buttonStyle(.borderedProminent)
                }
            } else if reports.sessions.isEmpty, reports.sessionsState != .loaded {
                ProgressView("Loading sessions…")
            } else if reports.sessions.isEmpty {
                ContentUnavailableView("No Sessions Yet", systemImage: "list.clipboard",
                                       description: Text("Open an attendance session from the dashboard first."))
            } else {
                List(reports.sessions) { session in
                    NavigationLink {
                        SessionReportView(sessionId: session.id, title: session.title)
                    } label: {
                        SessionSummaryRow(session: session)
                    }
                }
                .refreshable { await reports.loadSessions() }
            }
        }
        .navigationTitle("Attendance Reports")
        .task { await reports.loadSessions() }
    }
}

private struct SessionSummaryRow: View {
    let session: AttendanceSessionSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(session.title).font(.headline)
                Spacer()
                StatusBadge(text: session.isOpen ? "Open" : "Closed", color: session.isOpen ? .green : .secondary)
            }
            Text("\(session.classroomName) · \(session.openedAt.formatted(date: .abbreviated, time: .shortened))")
                .font(.subheadline).foregroundStyle(.secondary)
            Text("\(session.presentCount) marked present" + (session.openedBy.map { " · \($0)" } ?? ""))
                .font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}

/// One session's report from the server: summary, present and absent students, and the PDF.
struct SessionReportView: View {
    let sessionId: Int
    let title: String

    @EnvironmentObject private var reports: AttendanceReportStore
    @State private var pdfURL: URL?
    @State private var previewURL: URL?
    @State private var exportError: String?

    private var report: SessionReport? {
        reports.report?.session.id == sessionId ? reports.report : nil
    }

    var body: some View {
        Group {
            if let report {
                content(report)
            } else if let message = reports.reportState.errorMessage {
                ContentUnavailableView {
                    Label("Can't Load Report", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(message)
                } actions: {
                    Button("Try Again") { Task { await reports.loadReport(sessionId: sessionId) } }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                ProgressView("Loading report…")
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        // An open session's report is provisional: it refreshes every second while on screen.
        .task(id: sessionId) { await reports.pollReport(sessionId: sessionId) }
        .quickLookPreview($previewURL)
        .alert("Couldn't Create the PDF", isPresented: Binding(
            get: { exportError != nil }, set: { if !$0 { exportError = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(exportError ?? "")
        }
    }

    private func content(_ report: SessionReport) -> some View {
        List {
            Section {
                ReportHeader(report: report)
                if !report.session.isFinal {
                    Label("Provisional: the session is still open, so more students may tap in.",
                          systemImage: "clock.badge.exclamationmark")
                        .font(.subheadline).foregroundStyle(.orange)
                }
            }

            let justTapped = report.presentStudents.filter { reports.newlyPresent.contains($0.username) }
            if !justTapped.isEmpty {
                Section {
                    ForEach(justTapped) { student in
                        StudentRow(student: student, present: true, isNew: true)
                            .listRowBackground(Color.green.opacity(0.18))
                    }
                } header: {
                    Label("Just Marked Present", systemImage: "wave.3.right")
                }
            }

            Section("Attendance Summary") {
                SummaryGrid(summary: report.summary)
                    .animation(.default, value: report.summary)
            }

            Section {
                NavigationLink {
                    StudentListView(sessionId: sessionId, present: true)
                } label: {
                    Label("View Present Students (\(report.summary.present))", systemImage: "person.fill.checkmark")
                }
                NavigationLink {
                    StudentListView(sessionId: sessionId, present: false)
                } label: {
                    Label("View Absent Students (\(report.summary.absent))", systemImage: "person.fill.xmark")
                }
            } footer: {
                Text("Present means CampusOS has an attendance record for this session. Everyone else on the class roster is absent.")
            }

            Section {
                Button {
                    Task { await exportPDF() }
                } label: {
                    HStack {
                        Label("Download / Share PDF", systemImage: "doc.richtext")
                        Spacer()
                        if reports.isExporting { ProgressView() }
                    }
                }
                .disabled(reports.isExporting)
                if let pdfURL {
                    ShareLink(item: pdfURL) {
                        Label("Share \(pdfURL.lastPathComponent)", systemImage: "square.and.arrow.up")
                    }
                }
            } footer: {
                Text("The PDF is generated by the CampusOS server from the same records.")
            }

            if !report.notEnrolledAttendees.isEmpty {
                Section {
                    ForEach(report.notEnrolledAttendees) { StudentRow(student: $0, present: true) }
                } header: {
                    Text("Attended but Not Enrolled")
                } footer: {
                    Text("Not counted in the totals. Enroll them in the classroom to include them.")
                }
            }
        }
        .refreshable { await reports.loadReport(sessionId: sessionId) }
    }

    private func exportPDF() async {
        do {
            let url = try await reports.exportPDF(sessionId: sessionId)
            pdfURL = url
            previewURL = url
        } catch {
            exportError = error.localizedDescription
        }
    }
}

private struct ReportHeader: View {
    let report: SessionReport

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(report.session.title).font(.title3.bold())
            Label("Classroom: \(report.classroom.name) (\(report.classroom.id))", systemImage: "building.2")
            if let faculty = report.faculty.name {
                Label(faculty, systemImage: "person.crop.square")
            }
            Label(timeRange, systemImage: "clock")
            Text("Session ID \(report.session.id)").font(.caption).foregroundStyle(.secondary)
        }
        .font(.subheadline)
    }

    private var timeRange: String {
        let start = report.session.openedAt.formatted(date: .abbreviated, time: .shortened)
        guard let end = report.session.closedAt else { return "\(start) – still open" }
        return "\(start) – \(end.formatted(date: .omitted, time: .shortened))"
    }
}

private struct SummaryGrid: View {
    let summary: SessionReport.Summary

    var body: some View {
        Grid(horizontalSpacing: 8, verticalSpacing: 8) {
            GridRow {
                tile("Total Students", "\(summary.totalStudents)", .primary)
                tile("Attendance", summary.percentageText, .indigo)
            }
            GridRow {
                tile("Present", "\(summary.present)", .green)
                tile("Absent", "\(summary.absent)", .red)
            }
        }
        .padding(.vertical, 4)
    }

    private func tile(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title.bold().monospacedDigit()).foregroundStyle(color)
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}

/// Present or absent students of one session. Reads the store and keeps polling, so a student
/// who taps in while this list is open moves to Present (and off Absent) within a second.
private struct StudentListView: View {
    let sessionId: Int
    let present: Bool

    @EnvironmentObject private var reports: AttendanceReportStore

    private var students: [SessionReport.Student] {
        guard let report = reports.report, report.session.id == sessionId else { return [] }
        return present ? report.presentStudents : report.absentStudents
    }

    var body: some View {
        List {
            if students.isEmpty {
                Text(present ? "Nobody has attendance recorded for this session." : "Nobody is absent.")
                    .foregroundStyle(.secondary)
            }
            ForEach(Array(students.enumerated()), id: \.element.id) { index, student in
                let isNew = present && reports.newlyPresent.contains(student.username)
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text("\(index + 1).").monospacedDigit().foregroundStyle(.secondary)
                    StudentRow(student: student, present: present, isNew: isNew)
                }
                .listRowBackground(isNew ? Color.green.opacity(0.18) : nil)
            }
        }
        .animation(.default, value: students)
        .navigationTitle(present ? "Present Students" : "Absent Students")
        // The report screen's refresh stops while this one is pushed, so keep it going here.
        .task(id: sessionId) { await reports.pollReport(sessionId: sessionId) }
    }
}

private struct StudentRow: View {
    let student: SessionReport.Student
    let present: Bool
    var isNew = false

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(student.name).font(.headline)
                Spacer()
                if isNew {
                    StatusBadge(text: "Just tapped", color: .green)
                }
                StatusBadge(text: present ? "PRESENT" : "ABSENT", color: present ? .green : .red)
            }
            Text(student.rollNumber.isEmpty ? student.username : student.rollNumber)
                .font(.subheadline.monospaced()).foregroundStyle(.secondary)
            // Only present students have a record; absent students are never shown with a scan.
            if present, let markedAt = student.markedAt {
                Label(markedAt.formatted(date: .omitted, time: .standard),
                      systemImage: student.source == .manual ? "hand.raised" : "wave.3.right")
                    .font(.caption).foregroundStyle(.secondary)
                    .accessibilityLabel(student.source == .manual
                                        ? "Added by faculty at \(markedAt.formatted(date: .omitted, time: .standard))"
                                        : "Card tapped at \(markedAt.formatted(date: .omitted, time: .standard))")
            }
        }
        .accessibilityElement(children: .combine)
    }
}
