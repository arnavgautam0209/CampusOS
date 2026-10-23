import SwiftUI

/// Faculty dashboard: open sessions, the live scan feed and reader status.
struct LiveAttendanceView: View {
    @EnvironmentObject private var store: AttendanceStore
    @State private var showingOpenSession = false
    @State private var sessionToClose: LiveSession?
    @State private var actionError: String?

    var body: some View {
        Group {
            if let live = store.live {
                dashboard(live)
            } else if let message = store.loadState.errorMessage {
                ContentUnavailableView {
                    Label("Can't Load Attendance", systemImage: "wifi.exclamationmark")
                } description: {
                    Text(message)
                } actions: {
                    Button("Try Again") { Task { await store.refreshLive() } }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                ProgressView("Connecting to readers…")
            }
        }
        .task { await store.poll(staff: true) }
        .sheet(isPresented: $showingOpenSession) {
            NavigationStack { OpenSessionView(classrooms: store.classroomsAvailableToOpen) }
        }
        .confirmationDialog(
            "Close \(sessionToClose?.title ?? "session")?",
            isPresented: Binding(get: { sessionToClose != nil }, set: { if !$0 { sessionToClose = nil } }),
            titleVisibility: .visible,
            presenting: sessionToClose
        ) { session in
            Button("Close Session", role: .destructive) { Task { await close(session) } }
        } message: { session in
            Text("Readers in \(session.classroomName) will stop marking attendance. \(session.records.count) present will be kept.")
        }
        .alert("Couldn't Update Session", isPresented: Binding(
            get: { actionError != nil }, set: { if !$0 { actionError = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(actionError ?? "")
        }
    }

    private func close(_ session: LiveSession) async {
        do {
            try await store.closeSession(session)
        } catch {
            actionError = error.localizedDescription
        }
    }

    private var openSessionButton: some View {
        let rooms = store.classroomsAvailableToOpen
        return VStack(alignment: .leading, spacing: 4) {
            Button {
                showingOpenSession = true
            } label: {
                Label("Open Session…", systemImage: "plus.circle.fill")
            }
            .disabled(rooms.isEmpty || store.isChangingSession)
            if rooms.isEmpty, store.live?.classrooms.isEmpty == false {
                Text("Every classroom already has an open session.")
                    .font(.caption).foregroundStyle(.secondary)
            } else if store.live?.classrooms.isEmpty == true {
                Text("No classrooms are set up yet. Add one in the admin site.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func dashboard(_ live: AttendanceLive) -> some View {
        List {
            Section {
                LiveStatusRow(lastUpdated: store.lastUpdated, errorMessage: store.loadState.errorMessage)
            }

            Section("Open Sessions") {
                if live.openSessions.isEmpty {
                    Text("No attendance session is open, so readers won't mark anyone present.")
                        .foregroundStyle(.secondary)
                }
                openSessionButton
            }
            ForEach(live.openSessions) { session in
                Section {
                    if session.records.isEmpty {
                        Text("Waiting for the first card tap…").foregroundStyle(.secondary)
                    }
                    ForEach(session.records) { attendee in
                        AttendeeRow(attendee: attendee)
                    }
                    Button(role: .destructive) {
                        sessionToClose = session
                    } label: {
                        Label("Close Session", systemImage: "stop.circle")
                    }
                    .disabled(store.isChangingSession)
                } header: {
                    SessionHeader(session: session)
                }
            }

            Section("Live Scan Feed") {
                if live.recentScans.isEmpty {
                    Text("No taps yet.").foregroundStyle(.secondary)
                }
                ForEach(live.recentScans) { scan in
                    ScanRow(scan: scan)
                        .listRowBackground(store.newScanIDs.contains(scan.id) ? Color.yellow.opacity(0.18) : nil)
                }
            }

            Section {
                ForEach(live.readers) { ReaderRow(reader: $0) }
            } header: {
                Text("Readers")
            } footer: {
                Text("A card tap shows a card was present, not who held it. Treat unknown or repeated taps as prompts to check, never as proof of misconduct.")
            }
        }
        .animation(.default, value: live)
        .refreshable { await store.refreshLive() }
    }
}

private struct SessionHeader: View {
    let session: LiveSession

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(session.title).font(.headline).foregroundStyle(.primary)
                Spacer()
                StatusBadge(text: "\(session.records.count) present", color: .green)
            }
            Text("\(session.classroomName) · opened \(session.openedAt.formatted(date: .omitted, time: .shortened))"
                 + (session.openedBy.map { " by \($0)" } ?? ""))
                .font(.caption)
        }
        .textCase(nil)
    }
}

private struct AttendeeRow: View {
    let attendee: SessionAttendee

    var body: some View {
        HStack {
            Image(systemName: attendee.source == .card ? "wave.3.right.circle.fill" : "hand.raised.circle.fill")
                .foregroundStyle(attendee.source == .card ? .indigo : .orange)
                .accessibilityLabel(attendee.source == .card ? "Card tap" : "Added by faculty")
            Text(attendee.student)
            Spacer()
            Text(attendee.markedAt.formatted(date: .omitted, time: .shortened))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct ScanRow: View {
    let scan: ReaderScan

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: scan.result.symbol)
                .font(.title3)
                .foregroundStyle(scan.result.color)
            VStack(alignment: .leading, spacing: 2) {
                Text(scan.student ?? "Card \(scan.uid)").font(.headline)
                Text("\(scan.detail) · \(scan.deviceId)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text(scan.createdAt.formatted(date: .omitted, time: .standard))
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}

private struct ReaderRow: View {
    let reader: CardReader

    private var location: String {
        if let lab = reader.labId { return "Lab door · \(lab)" }
        return reader.classroomId ?? "Not assigned"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Label(reader.name, systemImage: "sensor.tag.radiowaves.forward")
                Spacer()
                if !reader.isActive {
                    StatusBadge(text: "Disabled", color: .red)
                } else if !reader.hasKey {
                    StatusBadge(text: "No key", color: .orange)
                }
            }
            Group {
                if let lastSeen = reader.lastSeenAt {
                    Text("\(location) · last tap \(lastSeen.formatted(.relative(presentation: .named)))")
                } else {
                    Text("\(location) · no taps yet")
                }
            }
            .font(.caption).foregroundStyle(.secondary)
        }
    }
}

extension ScanResult {
    var symbol: String {
        switch self {
        case .marked: return "checkmark.circle.fill"
        case .duplicate: return "arrow.triangle.2.circlepath.circle.fill"
        case .unknownCard: return "questionmark.circle.fill"
        case .noSession: return "clock.badge.xmark"
        case .wrongClassroom: return "exclamationmark.triangle.fill"
        case .granted: return "door.left.hand.open"
        case .alreadyCheckedIn: return "arrow.triangle.2.circlepath.circle.fill"
        case .denied: return "lock.fill"
        case .other: return "circle"
        }
    }

    var color: Color {
        switch self {
        case .marked, .granted: return .green
        case .duplicate, .alreadyCheckedIn: return .yellow
        case .unknownCard, .noSession, .wrongClassroom, .denied: return .red
        case .other: return .gray
        }
    }
}
