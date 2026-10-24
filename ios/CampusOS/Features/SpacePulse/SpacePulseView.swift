import SwiftUI

/// SpacePulse: find a free room for a day, book it, check in, and (faculty) see usage.
struct SpacePulseView: View {
    @EnvironmentObject private var spaces: SpacesStore
    @EnvironmentObject private var auth: AuthManager
    @State private var day = Calendar.current.startOfDay(for: Date())
    @State private var filter: RoomKind? = nil
    @State private var booking: CampusRoom?
    @State private var showingSignIn = false
    @State private var errorMessage: String?

    private var isStaff: Bool { auth.currentUser?.role.isStaff == true }
    private var days: [Date] {
        (0..<7).compactMap { Calendar.current.date(byAdding: .day, value: $0, to: Calendar.current.startOfDay(for: Date())) }
    }

    var body: some View {
        content
            .navigationTitle("SpacePulse")
            .task(id: "\(auth.isSignedIn)-\(isStaff)-\(day.timeIntervalSince1970)") {
                guard auth.isSignedIn else { return spaces.reset() }
                await spaces.load(day: day, staff: isStaff)
            }
            .sheet(item: $booking) { room in
                if let availability = spaces.availability {
                    NavigationStack {
                        RoomBookingSheet(room: room, day: day, dayStart: availability.dayStart,
                                         dayEnd: availability.dayEnd)
                    }
                }
            }
            .sheet(isPresented: $showingSignIn) {
                NavigationStack { SignInView(showsCancel: true) }
            }
            .alert("Couldn't Update Booking", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
            ) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(errorMessage ?? "")
            }
    }

    @ViewBuilder
    private var content: some View {
        if !auth.isSignedIn {
            ContentUnavailableView {
                Label("Sign In to Find a Room", systemImage: "building.2")
            } description: {
                Text("See which classrooms, study rooms and meeting rooms are free, and book one.")
            } actions: {
                Button("Sign In") { showingSignIn = true }
                    .buttonStyle(.borderedProminent)
            }
        } else if let availability = spaces.availability {
            list(availability)
        } else if let message = spaces.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load Rooms", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await spaces.load(day: day, staff: isStaff) } }
                    .buttonStyle(.borderedProminent)
            }
        } else {
            ProgressView("Loading rooms…")
        }
    }

    private func list(_ availability: SpaceAvailability) -> some View {
        let rooms = availability.rooms.filter { filter == nil || $0.kind == filter }
        return List {
            Section {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(days, id: \.self) { candidate in
                            DayChip(day: candidate, selected: Calendar.current.isDate(candidate, inSameDayAs: day)) {
                                day = candidate
                            }
                        }
                    }
                    .padding(.vertical, 2)
                }
                Picker("Room type", selection: $filter) {
                    Text("All").tag(RoomKind?.none)
                    Text("Study").tag(RoomKind?.some(.studyRoom))
                    Text("Meeting").tag(RoomKind?.some(.meetingRoom))
                    Text("Class").tag(RoomKind?.some(.classroom))
                }
                .pickerStyle(.segmented)
            }

            Section {
                NavigationLink {
                    FindRoomView()
                } label: {
                    Label("Find Best Room", systemImage: "sparkle.magnifyingglass")
                        .font(.headline)
                }
                if isStaff {
                    NavigationLink {
                        ManageTimetablesView()
                    } label: {
                        Label("Manage Timetables", systemImage: "calendar.badge.clock")
                    }
                }
            } footer: {
                Text("Tell SpacePulse your group size and time; it suggests the classroom that fits best.")
            }

            if !spaces.upcoming.isEmpty {
                Section("Your Room Bookings") {
                    ForEach(spaces.upcoming) { booking in
                        MyRoomBookingRow(booking: booking, isBusy: spaces.busyBookingID == booking.id,
                                         checkIn: { act { try await spaces.checkIn(booking, day: day) } },
                                         cancel: { act { try await spaces.cancel(booking, day: day) } })
                    }
                }
            }

            Section {
                if rooms.isEmpty {
                    Text("No rooms of this type.").foregroundStyle(.secondary)
                }
                ForEach(rooms) { room in
                    Button {
                        if room.isBookable { booking = room }
                    } label: {
                        RoomRow(room: room, dayStart: availability.dayStart, dayEnd: availability.dayEnd,
                                isToday: Calendar.current.isDateInToday(day))
                    }
                    .buttonStyle(.plain)
                    .disabled(!room.isBookable)
                }
            } header: {
                Text("Rooms · \(day.formatted(.dateTime.weekday(.wide).day().month(.abbreviated)))")
            } footer: {
                Text("Bars show 08:00–20:00: classes are orange, your bookings purple. Check in from 10 minutes before your start; bookings without a check-in 15 minutes after the start are released for others.")
            }

            if isStaff, !spaces.usage.isEmpty {
                Section("Usage · Last 7 Days") {
                    ForEach(spaces.usage) { UsageRow(usage: $0) }
                }
            }
        }
        .refreshable { await spaces.load(day: day, staff: isStaff) }
    }

    private func act(_ action: @escaping () async throws -> Void) {
        Task {
            do {
                try await action()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}

private struct DayChip: View {
    let day: Date
    let selected: Bool
    let select: () -> Void

    var body: some View {
        Button(action: select) {
            VStack(spacing: 2) {
                Text(Calendar.current.isDateInToday(day) ? "Today" : day.formatted(.dateTime.weekday(.abbreviated)))
                    .font(.caption)
                Text(day.formatted(.dateTime.day())).font(.headline)
            }
            .frame(width: 54, height: 50)
            .background(selected ? Color.indigo : Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
            .foregroundStyle(selected ? .white : .primary)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct RoomRow: View {
    let room: CampusRoom
    let dayStart: Date
    let dayEnd: Date
    let isToday: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: room.kind.symbol)
                    .font(.title3).foregroundStyle(.teal)
                    .frame(width: 36, height: 36)
                    .background(.teal.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
                VStack(alignment: .leading, spacing: 2) {
                    Text(room.name).font(.headline)
                    Text("\(room.kind.label) · \(room.location) · \(room.capacity) seats")
                        .font(.caption).foregroundStyle(.secondary)
                    if !room.features.isEmpty {
                        Text(room.features.joined(separator: " · ")).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 4)
                statusBadge
            }
            DayTimeline(slots: room.busy, lectures: room.lectures, dayStart: dayStart, dayEnd: dayEnd)
            if !room.isBookable {
                Text("Timetabled: faculty book this room.").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }

    @ViewBuilder
    private var statusBadge: some View {
        if isToday {
            if room.inClassNow {
                StatusBadge(text: "Class now", color: .orange)
            } else if room.freeNow {
                StatusBadge(text: "Free now", color: .green)
            } else {
                StatusBadge(text: "Booked now", color: .red)
            }
        }
    }
}

/// A 08:00–20:00 bar with booked periods filled in.
private struct DayTimeline: View {
    let slots: [CampusRoom.BusySlot]
    var lectures: [CampusRoom.Lecture] = []
    let dayStart: Date
    let dayEnd: Date

    var body: some View {
        GeometryReader { proxy in
            let total = dayEnd.timeIntervalSince(dayStart)
            ZStack(alignment: .leading) {
                Capsule().fill(Color.green.opacity(0.15))
                // Timetabled classes (orange) take the whole room.
                ForEach(Array(lectures.enumerated()), id: \.offset) { _, lecture in
                    let start = max(0, lecture.start.timeIntervalSince(dayStart)) / total
                    let end = min(total, lecture.end.timeIntervalSince(dayStart)) / total
                    Capsule()
                        .fill(Color.orange)
                        .frame(width: max(4, proxy.size.width * (end - start)))
                        .offset(x: proxy.size.width * start)
                }
                ForEach(Array(slots.enumerated()), id: \.offset) { _, slot in
                    let start = max(0, slot.start.timeIntervalSince(dayStart)) / total
                    let end = min(total, slot.end.timeIntervalSince(dayStart)) / total
                    Capsule()
                        .fill(slot.mine ? Color.purple : Color.gray.opacity(0.6))
                        .frame(width: max(4, proxy.size.width * (end - start)))
                        .offset(x: proxy.size.width * start)
                }
            }
        }
        .frame(height: 8)
        .accessibilityElement()
        .accessibilityLabel(slots.isEmpty && lectures.isEmpty ? "Free all day" : (lectures.map {
            "\($0.activity) \($0.start.formatted(date: .omitted, time: .shortened)) to \($0.end.formatted(date: .omitted, time: .shortened))"
        } + slots.map {
            "Booked \($0.start.formatted(date: .omitted, time: .shortened)) to \($0.end.formatted(date: .omitted, time: .shortened))"
        }).joined(separator: ", "))
    }
}

private struct MyRoomBookingRow: View {
    let booking: RoomBooking
    let isBusy: Bool
    let checkIn: () -> Void
    let cancel: () -> Void

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            VStack(alignment: .leading, spacing: 6) {
                Text(booking.roomName).font(.headline)
                Text("\(booking.start.formatted(date: .abbreviated, time: .shortened))–\(booking.end.formatted(date: .omitted, time: .shortened)) · \(booking.attendees) \(booking.attendees == 1 ? "person" : "people")")
                    .font(.subheadline).foregroundStyle(.secondary)
                Text(booking.mode == .shared
                     ? "Shared study · \(booking.attendees)\(booking.roomCapacity.map { " of \($0)" } ?? "") seats"
                     : "Whole room")
                    .font(.caption).foregroundStyle(.secondary)
                if let note = booking.note {
                    Label(note, systemImage: "arrow.triangle.swap")
                        .font(.caption).foregroundStyle(.orange)
                }
                if !booking.purpose.isEmpty {
                    Text(booking.purpose).font(.caption).foregroundStyle(.secondary)
                }
                if let checkedIn = booking.checkedInAt {
                    Label("Checked in at \(checkedIn.formatted(date: .omitted, time: .shortened))",
                          systemImage: "checkmark.circle.fill")
                        .font(.subheadline.weight(.semibold)).foregroundStyle(.green)
                } else if isBusy {
                    ProgressView()
                } else {
                    HStack(spacing: 12) {
                        if booking.canCheckIn(now: context.date) {
                            Button("Check In", action: checkIn)
                                .buttonStyle(.borderedProminent)
                                .tint(.green)
                        }
                        Button("Cancel", role: .destructive, action: cancel)
                            .buttonStyle(.bordered)
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }
}

private struct UsageRow: View {
    let usage: RoomUsage

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(usage.roomName)
                Spacer()
                Text("\(usage.utilizationPct)%").font(.subheadline.monospacedDigit().weight(.semibold))
            }
            ProgressView(value: Double(min(usage.utilizationPct, 100)), total: 100)
                .tint(.teal)
            Text("\(usage.bookings) bookings · \(String(format: "%.1f", usage.bookedHours)) h · \(usage.noShows) no-shows")
                .font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}
