import SwiftUI

/// Student: enter a group size and time, get the best-fitting free classroom from the server, book seats.
struct FindRoomView: View {
    @EnvironmentObject private var finder: RoomFinderStore
    @EnvironmentObject private var spaces: SpacesStore
    @EnvironmentObject private var auth: AuthManager
    @State private var purpose = ""
    @State private var confirmation: String?
    @State private var errorMessage: String?

    private let durations = [30, 60, 90, 120]
    private var lastDay: Date {
        Calendar.current.date(byAdding: .day, value: 30, to: Calendar.current.startOfDay(for: Date())) ?? Date()
    }

    var body: some View {
        Form {
            Section("Your Group") {
                Stepper(value: $finder.search.groupSize, in: 1...500) {
                    HStack {
                        Text("Group size")
                        Spacer()
                        TextField("People", value: $finder.search.groupSize, format: .number)
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                            .frame(width: 60)
                            .accessibilityLabel("Group size")
                        Text(finder.search.groupSize == 1 ? "person" : "people").foregroundStyle(.secondary)
                    }
                }
                Picker("Classroom use", selection: $finder.search.mode) {
                    ForEach(BookingMode.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                Text(finder.search.mode == .shared
                     ? "Share the room: your group takes only the seats it needs."
                     : "Book the whole room: no other group can use it.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section("When") {
                DatePicker("Date", selection: $finder.search.day, in: Calendar.current.startOfDay(for: Date())...lastDay,
                           displayedComponents: .date)
                DatePicker("Start time", selection: $finder.search.startTime, displayedComponents: .hourAndMinute)
                Picker("Duration", selection: $finder.search.minutes) {
                    ForEach(durations, id: \.self) { Text($0 < 60 ? "\($0) min" : "\(Double($0) / 60, specifier: "%g") h").tag($0) }
                }
                TextField("Purpose (optional)", text: $purpose)
            }

            Section {
                Button {
                    Task { await finder.find() }
                } label: {
                    HStack {
                        Spacer()
                        if finder.searchState.isLoading {
                            ProgressView()
                        } else {
                            Label("Find Best Room", systemImage: "sparkle.magnifyingglass").font(.headline)
                        }
                        Spacer()
                    }
                }
                .disabled(finder.searchState.isLoading)
            } footer: {
                Text("CampusOS checks the class timetable, other groups' bookings and room sizes, then suggests the room that leaves the fewest seats empty.")
            }

            results
        }
        .navigationTitle("Find a Room")
        .scrollDismissesKeyboard(.interactively)
        .alert("Booking Confirmed", isPresented: Binding(get: { confirmation != nil }, set: { if !$0 { confirmation = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(confirmation ?? "")
        }
        .alert("Couldn't Book", isPresented: Binding(get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(errorMessage ?? "")
        }
    }

    @ViewBuilder
    private var results: some View {
        if let message = finder.searchState.errorMessage {
            Section {
                Label(message, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
            }
        } else if let result = finder.result {
            Section {
                if let timetable = result.timetable {
                    Label("Timetable v\(timetable.version): \(timetable.name)", systemImage: "calendar")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let best = result.recommended {
                    RecommendedRoomCard(room: best, result: result, isBooking: finder.bookingRoomID == best.id) {
                        Task { await book(best) }
                    }
                    .disabled(finder.bookingRoomID != nil)
                } else {
                    ContentUnavailableView("No Room Available", systemImage: "building.2.crop.circle",
                                           description: Text(result.message))
                }
            } header: {
                Text("\(result.start.formatted(.dateTime.weekday(.wide).day().month())) · \(result.start.formatted(date: .omitted, time: .shortened))–\(result.end.formatted(date: .omitted, time: .shortened))")
            }

            if !result.alternatives.isEmpty {
                Section("Other Rooms That Fit") {
                    ForEach(result.alternatives) { room in
                        RoomFitRow(room: room, groupSize: result.groupSize, mode: result.mode,
                                   isBooking: finder.bookingRoomID == room.id) {
                            Task { await book(room) }
                        }
                        .disabled(finder.bookingRoomID != nil)
                    }
                }
            }

            if !result.unavailable.isEmpty {
                Section("Not Available Then") {
                    ForEach(result.unavailable) { room in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                Text(room.name)
                                Spacer()
                                Text("\(room.availableSeats)/\(room.capacity)")
                                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                            }
                            Text(room.reason ?? "").font(.caption).foregroundStyle(.secondary)
                        }
                        .accessibilityElement(children: .combine)
                    }
                }
            }
        }
    }

    private func book(_ room: RoomFit) async {
        let group = finder.search.groupSize
        do {
            try await finder.book(room, purpose: purpose)
            confirmation = "Your classroom booking is confirmed: \(room.name), \(group) \(group == 1 ? "seat" : "seats"). It's in Your Room Bookings."
            // Refresh SpacePulse's day view and bookings list.
            await spaces.load(day: Calendar.current.startOfDay(for: finder.search.day),
                              staff: auth.currentUser?.role.isStaff == true)
        } catch {
            errorMessage = error.localizedDescription
            await finder.find()
        }
    }
}

/// The best-fit room: total capacity, seats free at that time, and seats left after the group.
private struct RecommendedRoomCard: View {
    let room: RoomFit
    let result: RoomSearchResult
    let isBooking: Bool
    let confirm: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    StatusBadge(text: "RECOMMENDED", color: .indigo)
                    Text(room.name).font(.title3.bold())
                    Text("\(room.id) · \(room.location)").font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: room.kind.symbol)
                    .font(.title2).foregroundStyle(.indigo)
                    .frame(width: 48, height: 48)
                    .background(.indigo.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
            }
            Label(result.message, systemImage: "checkmark.seal.fill")
                .font(.subheadline.weight(.semibold)).foregroundStyle(.green)
            SeatBar(capacity: room.capacity, taken: room.capacity - room.availableSeats,
                    yours: result.mode == .exclusive ? room.availableSeats : result.groupSize)
            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                stat("Total capacity", room.capacity)
                stat("Available before booking", room.availableSeats)
                stat(result.mode == .exclusive ? "Your group (whole room)" : "Seats requested", result.groupSize)
                stat(result.mode == .exclusive ? "Empty seats in your room" : "Available after booking",
                     room.seatsAfterBooking, highlight: true)
            }
            Button(action: confirm) {
                HStack {
                    Spacer()
                    if isBooking { ProgressView().tint(.white) } else { Text("Confirm Booking").font(.headline) }
                    Spacer()
                }
                .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            .tint(.indigo)
        }
        .padding(.vertical, 6)
    }

    private func stat(_ label: String, _ value: Int, highlight: Bool = false) -> some View {
        GridRow {
            Text(label).foregroundStyle(.secondary)
            Text("\(value)").monospacedDigit().fontWeight(highlight ? .bold : .regular)
                .foregroundStyle(highlight ? .green : .primary)
                .gridColumnAlignment(.trailing)
        }
        .font(.subheadline)
    }
}

private struct RoomFitRow: View {
    let room: RoomFit
    let groupSize: Int
    let mode: BookingMode
    let isBooking: Bool
    let book: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(room.name).font(.headline)
                    Text("\(room.availableSeats) of \(room.capacity) seats free · \(room.seatsAfterBooking) left after your group")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if isBooking {
                    ProgressView()
                } else {
                    Button("Book", action: book).buttonStyle(.bordered)
                }
            }
            SeatBar(capacity: room.capacity, taken: room.capacity - room.availableSeats,
                    yours: mode == .exclusive ? room.availableSeats : groupSize)
        }
        .padding(.vertical, 2)
    }
}

/// Seats taken by others (gray), your group (indigo) and still free (green), out of the room's capacity.
struct SeatBar: View {
    let capacity: Int
    let taken: Int
    let yours: Int

    var body: some View {
        GeometryReader { proxy in
            let total = Double(max(capacity, 1))
            let takenWidth = proxy.size.width * Double(max(taken, 0)) / total
            let yoursWidth = proxy.size.width * Double(max(min(yours, capacity - taken), 0)) / total
            ZStack(alignment: .leading) {
                Capsule().fill(Color.green.opacity(0.25))
                HStack(spacing: 0) {
                    Rectangle().fill(Color.gray.opacity(0.6)).frame(width: takenWidth)
                    Rectangle().fill(Color.indigo).frame(width: yoursWidth)
                }
                .clipShape(Capsule())
            }
        }
        .frame(height: 10)
        .accessibilityElement()
        .accessibilityLabel("\(taken) seats taken by others, \(yours) for your group, \(max(capacity - taken - yours, 0)) free, of \(capacity)")
    }
}
