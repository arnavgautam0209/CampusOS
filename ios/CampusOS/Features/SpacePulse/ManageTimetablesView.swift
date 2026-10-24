import SwiftUI
import UniformTypeIdentifiers

/// Faculty: the active timetable, uploading a new CSV, reviewing it, and activating it.
struct ManageTimetablesView: View {
    @EnvironmentObject private var timetables: TimetableStore
    @State private var importing = false
    @State private var uploadedID: Int?
    @State private var uploadError: String?

    var body: some View {
        List {
            if let message = timetables.loadState.errorMessage {
                Label(message, systemImage: "wifi.exclamationmark").foregroundStyle(.orange)
            }

            Section("Active Timetable") {
                if let active = timetables.active {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(active.name).font(.headline)
                            Spacer()
                            StatusBadge(text: "v\(active.version)", color: .green)
                        }
                        Text("\(active.classCount) weekly classes" + (active.activatedAt.map {
                            " · active since \($0.formatted(date: .abbreviated, time: .shortened))" } ?? ""))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    NavigationLink {
                        WeeklyScheduleView(timetable: active)
                    } label: {
                        Label("View Weekly Schedule", systemImage: "calendar.day.timeline.left")
                    }
                } else if timetables.loadState == .loaded {
                    Text("No timetable is active, so no classes block rooms.").foregroundStyle(.secondary)
                } else {
                    ProgressView()
                }
            }

            Section {
                Button {
                    importing = true
                } label: {
                    HStack {
                        Label("Upload Timetable (CSV)…", systemImage: "square.and.arrow.up.on.square")
                        Spacer()
                        if timetables.isUploading { ProgressView() }
                    }
                }
                .disabled(timetables.isUploading)
            } header: {
                Text("Upload")
            } footer: {
                Text("Columns: day,start,end,room_id,activity (e.g. Monday,11:00,12:00,ECE-101,Microcontrollers). The server checks every row; the new timetable isn't used until you activate it.")
            }

            Section("Versions") {
                ForEach(timetables.versions) { version in
                    NavigationLink {
                        TimetableReviewView(timetableId: version.id)
                    } label: {
                        VersionRow(timetable: version)
                    }
                }
            }

            Section {
                NavigationLink {
                    GroupReservationsView()
                } label: {
                    Label("Group Reservations (\(timetables.reservations.count))", systemImage: "person.3")
                }
                NavigationLink {
                    FindRoomView()
                } label: {
                    Label("Check Room Occupancy", systemImage: "chart.bar.doc.horizontal")
                }
            }

            if !timetables.history.isEmpty {
                Section("Recent Changes") {
                    ForEach(timetables.history.prefix(10)) { event in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(event.label + (event.timetableVersion.map { " · v\($0)" } ?? "")).font(.subheadline)
                            if !event.detail.isEmpty {
                                Text(event.detail).font(.caption).foregroundStyle(.secondary)
                            }
                            Text("\(event.actor ?? "System") · \(event.createdAt.formatted(date: .abbreviated, time: .shortened))")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("Manage Timetables")
        .task { await timetables.load(staff: true) }
        .refreshable { await timetables.load(staff: true) }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.commaSeparatedText, .plainText, .text]) { result in
            Task { await handleImport(result) }
        }
        .navigationDestination(item: $uploadedID) { id in
            TimetableReviewView(timetableId: id)
        }
        .alert("Timetable Not Accepted", isPresented: Binding(
            get: { uploadError != nil }, set: { if !$0 { uploadError = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(uploadError ?? "")
        }
    }

    /// Reads the chosen file's text and sends it to the server, which validates and stores it.
    private func handleImport(_ result: Result<URL, Error>) async {
        do {
            let url = try result.get()
            let csv = try Self.readText(at: url)
            uploadedID = try await timetables.upload(filename: url.lastPathComponent, csv: csv).id
        } catch {
            uploadError = error.localizedDescription
        }
    }

    nonisolated static func readText(at url: URL) throws -> String {
        // Files from the Files app are outside the sandbox until access is granted.
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: url)
        guard data.count <= 200_000 else {
            throw APIError.invalid("The file is larger than 200 KB.")
        }
        guard let text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) else {
            throw APIError.invalid("The file isn't readable text.")
        }
        return text
    }
}

private struct VersionRow: View {
    let timetable: Timetable

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text("v\(timetable.version) · \(timetable.name)").font(.subheadline.weight(.semibold))
                Spacer()
                StatusBadge(text: timetable.status.label, color: color)
            }
            Text("\(timetable.classCount) classes · " + (timetable.sourceFilename.isEmpty ? "" : "\(timetable.sourceFilename) · ")
                 + "\(timetable.uploadedBy ?? "Demo seed"), \(timetable.createdAt.formatted(date: .abbreviated, time: .shortened))")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var color: Color {
        switch timetable.status {
        case .active: return .green
        case .draft: return .orange
        default: return .secondary
        }
    }
}

/// One version before (or after) activation: what changes, which bookings clash, and Activate.
struct TimetableReviewView: View {
    let timetableId: Int

    @EnvironmentObject private var timetables: TimetableStore
    @State private var cancelling: TimetableConflict?
    @State private var errorMessage: String?
    @State private var activated = false

    var body: some View {
        Group {
            if let review = timetables.review, review.id == timetableId {
                content(review)
            } else if let message = timetables.reviewState.errorMessage {
                ContentUnavailableView {
                    Label("Can't Load Timetable", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(message)
                } actions: {
                    Button("Try Again") { Task { await timetables.loadReview(id: timetableId) } }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                ProgressView("Checking timetable…")
            }
        }
        .navigationTitle("Review Timetable")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: timetableId) { await timetables.loadReview(id: timetableId) }
        .confirmationDialog("Cancel this booking?", isPresented: Binding(
            get: { cancelling != nil }, set: { if !$0 { cancelling = nil } }), titleVisibility: .visible,
            presenting: cancelling
        ) { conflict in
            Button("Cancel \(conflict.bookedBy)'s Booking", role: .destructive) {
                Task { await act { try await timetables.resolve(conflict, action: .cancel) } }
            }
        } message: { conflict in
            Text("\(conflict.bookedBy) will see that it was cancelled because of \(conflict.clashesWith). This is logged.")
        }
        .alert("Couldn't Update", isPresented: Binding(
            get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(errorMessage ?? "")
        }
        .alert("Timetable Activated", isPresented: $activated) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("Room availability and recommendations now use \(timetables.review?.name ?? "this timetable").")
        }
    }

    private func content(_ review: Timetable) -> some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(review.name).font(.headline)
                        Spacer()
                        StatusBadge(text: "v\(review.version) · \(review.status.label)",
                                    color: review.status == .active ? .green : .orange)
                    }
                    if !review.sourceFilename.isEmpty {
                        Label(review.sourceFilename, systemImage: "doc.text").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Label("All \(review.classCount) rows passed validation", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                NavigationLink {
                    WeeklyScheduleView(timetable: review)
                } label: {
                    Label("Preview Weekly Schedule", systemImage: "calendar")
                }
            }

            if review.status == .active {
                Section {
                    Label("This is the active timetable: room availability uses it now.", systemImage: "checkmark.seal.fill")
                        .foregroundStyle(.green)
                }
            } else if let preview = timetables.preview {
                Section {
                    if preview.changes.isEmpty {
                        Text("No rooms change.").foregroundStyle(.secondary)
                    }
                    ForEach(preview.changes) { ChangeRow(change: $0) }
                } header: {
                    Text(preview.againstVersion.map { "Changes vs Active v\($0)" } ?? "Changes")
                } footer: {
                    Text("Occupied: students can't book the room then. Freed: the room opens up for bookings.")
                }
            }

            if review.status != .active {
                Section {
                    if timetables.conflicts.isEmpty {
                        Label("No existing bookings clash with this timetable.", systemImage: "checkmark.shield")
                            .foregroundStyle(.green)
                    }
                    ForEach(timetables.conflicts) { conflict in
                        ConflictRow(conflict: conflict, isBusy: timetables.resolvingID == conflict.bookingId,
                                    reassign: { Task { await act { try await timetables.resolve(conflict, action: .reassign) } } },
                                    cancel: { cancelling = conflict })
                    }
                } header: {
                    Text("Booking Conflicts (\(timetables.conflicts.count))")
                } footer: {
                    if !timetables.conflicts.isEmpty {
                        Text("Activation is blocked until every clashing booking is moved or cancelled. Students are never removed silently.")
                    }
                }

                Section {
                    Button {
                        Task { await activate() }
                    } label: {
                        HStack {
                            Spacer()
                            if timetables.isActivating { ProgressView() } else {
                                Text(review.status == .archived ? "Re-activate This Version" : "Activate Timetable")
                                    .font(.headline)
                            }
                            Spacer()
                        }
                    }
                    .disabled(!timetables.canActivate || timetables.isActivating)
                } footer: {
                    Text("Replaces the active timetable. The current one is kept and can be re-activated.")
                }
            }
        }
        .refreshable { await timetables.loadReview(id: timetableId) }
    }

    private func activate() async {
        do {
            try await timetables.activate()
            activated = true
        } catch {
            errorMessage = error.localizedDescription
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

private struct ChangeRow: View {
    let change: TimetableChange

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol).foregroundStyle(color).frame(width: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(change.roomId) · \(change.day) \(change.start)–\(change.end)").font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var symbol: String {
        switch change.change {
        case .occupied: return "lock.fill"
        case .freed: return "lock.open.fill"
        default: return "arrow.triangle.2.circlepath"
        }
    }

    private var color: Color {
        switch change.change {
        case .occupied: return .red
        case .freed: return .green
        default: return .blue
        }
    }

    private var detail: String {
        switch change.change {
        case .occupied: return "Becomes occupied: \(change.after ?? "")"
        case .freed: return "Becomes free (was \(change.before ?? ""))"
        default: return "\(change.before ?? "") → \(change.after ?? "")"
        }
    }
}

private struct ConflictRow: View {
    let conflict: TimetableConflict
    let isBusy: Bool
    let reassign: () -> Void
    let cancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("\(conflict.bookedBy) · \(conflict.attendees) \(conflict.attendees == 1 ? "person" : "people")")
                .font(.headline)
            Text("\(conflict.roomName) · \(conflict.start.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute()))–\(conflict.end.formatted(date: .omitted, time: .shortened))")
                .font(.subheadline)
            Label("Clashes with \(conflict.clashesWith)", systemImage: "exclamationmark.triangle.fill")
                .font(.caption).foregroundStyle(.orange)
            if isBusy {
                ProgressView()
            } else {
                HStack(spacing: 10) {
                    if let room = conflict.suggestedRoomId {
                        Button("Move to \(room)", action: reassign)
                            .buttonStyle(.borderedProminent)
                    }
                    Button("Cancel Booking", role: .destructive, action: cancel)
                        .buttonStyle(.bordered)
                }
                if conflict.suggestedRoomId == nil {
                    Text("No other room fits this group then.").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

/// A timetable's classes by weekday.
struct WeeklyScheduleView: View {
    let timetable: Timetable

    @EnvironmentObject private var timetables: TimetableStore
    @State private var entries: [TimetableClass]?

    var body: some View {
        List {
            let days = Dictionary(grouping: entries ?? [], by: \.weekday)
            ForEach(days.keys.sorted(), id: \.self) { weekday in
                Section(days[weekday]?.first?.day ?? "") {
                    ForEach(days[weekday] ?? []) { item in
                        HStack(alignment: .firstTextBaseline) {
                            Text("\(item.start)–\(item.end)").font(.subheadline.monospacedDigit())
                                .frame(width: 100, alignment: .leading)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.activity)
                                Text(item.roomId).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            if entries == nil {
                ProgressView()
            }
        }
        .navigationTitle("v\(timetable.version) Schedule")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            entries = timetable.entries
            if entries == nil {
                entries = (try? await timetables.fetchEntries(id: timetable.id)) ?? []
            }
        }
    }
}

/// Faculty: every upcoming group reservation.
private struct GroupReservationsView: View {
    @EnvironmentObject private var timetables: TimetableStore

    var body: some View {
        List {
            if timetables.reservations.isEmpty {
                Text("No upcoming room bookings.").foregroundStyle(.secondary)
            }
            ForEach(timetables.reservations) { booking in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(booking.roomName).font(.headline)
                        Spacer()
                        StatusBadge(text: booking.mode == .shared ? "\(booking.attendees) seats" : "Whole room",
                                    color: booking.mode == .shared ? .indigo : .purple)
                    }
                    Text("\(booking.start.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute()))–\(booking.end.formatted(date: .omitted, time: .shortened)) · \(booking.bookedBy)")
                        .font(.subheadline).foregroundStyle(.secondary)
                    if !booking.purpose.isEmpty {
                        Text(booking.purpose).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Group Reservations")
        .refreshable { await timetables.load(staff: true) }
    }
}
