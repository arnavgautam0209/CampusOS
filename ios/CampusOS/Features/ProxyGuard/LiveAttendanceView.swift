import SwiftUI

/// Faculty dashboard: open sessions, the live scan feed and reader status.
struct LiveAttendanceView: View {
    @EnvironmentObject private var store: AttendanceStore

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
    }

    private func dashboard(_ live: AttendanceLive) -> some View {
        List {
            Section {
                LiveStatusRow(lastUpdated: store.lastUpdated, errorMessage: store.loadState.errorMessage)
            }

            if live.openSessions.isEmpty {
                Section("Open Sessions") {
                    Text("No attendance session is open. Open one in the admin site under Attendance → Attendance sessions.")
                        .foregroundStyle(.secondary)
                }
            }
            ForEach(live.openSessions) { session in
                Section {
                    if session.records.isEmpty {
                        Text("Waiting for the first card tap…").foregroundStyle(.secondary)
                    }
                    ForEach(session.records) { attendee in
                        AttendeeRow(attendee: attendee)
                    }
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
                Text("\(scan.result.label) · \(scan.deviceId)")
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
                    Text("\(reader.classroomId ?? "No room") · last tap \(lastSeen.formatted(.relative(presentation: .named)))")
                } else {
                    Text("\(reader.classroomId ?? "No room") · no taps yet")
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
        case .other: return "circle"
        }
    }

    var color: Color {
        switch self {
        case .marked: return .green
        case .duplicate: return .yellow
        case .unknownCard, .noSession, .wrongClassroom: return .red
        case .other: return .gray
        }
    }
}
