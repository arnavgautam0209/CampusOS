import SwiftUI

/// Book a room: pick a free start time, length, people and purpose. The server
/// re-checks conflicts, capacity and permission.
struct RoomBookingSheet: View {
    let room: CampusRoom
    let day: Date
    let dayStart: Date
    let dayEnd: Date

    @EnvironmentObject private var spaces: SpacesStore
    @Environment(\.dismiss) private var dismiss
    @State private var minutes = 60
    @State private var start: Date?
    @State private var attendees = 1
    @State private var purpose = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private var freeStarts: [Date] {
        room.freeStarts(dayStart: dayStart, dayEnd: dayEnd, minutes: minutes, now: Date())
    }

    var body: some View {
        Form {
            Section {
                LabeledContent("Room", value: room.name)
                LabeledContent("Where", value: room.location)
                LabeledContent("Day", value: day.formatted(.dateTime.weekday(.wide).day().month(.wide)))
            }
            Section("Length") {
                Picker("Length", selection: $minutes) {
                    Text("30 min").tag(30)
                    Text("1 hour").tag(60)
                    Text("2 hours").tag(120)
                }
                .pickerStyle(.segmented)
            }
            Section {
                if freeStarts.isEmpty {
                    Text("No free \(minutes)-minute slots left on this day.").foregroundStyle(.secondary)
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 96))], spacing: 8) {
                        ForEach(freeStarts, id: \.self) { slot in
                            Button {
                                start = slot
                            } label: {
                                Text(slot.formatted(date: .omitted, time: .shortened))
                                    .font(.subheadline.monospacedDigit())
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.8)
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            .tint(start == slot ? .indigo : .gray)
                        }
                    }
                    .padding(.vertical, 4)
                }
            } header: {
                Text("Start Time")
            }
            Section("Details") {
                Stepper("People: \(attendees)", value: $attendees, in: 1...max(1, room.capacity))
                TextField("Purpose (optional), e.g. Project meeting", text: $purpose)
            }
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Book Room")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: minutes) { _, _ in
            if let start, !freeStarts.contains(start) { self.start = nil }
        }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                if isSubmitting {
                    ProgressView()
                } else {
                    Button("Book") { Task { await submit() } }
                        .disabled(start == nil)
                }
            }
        }
        .interactiveDismissDisabled(isSubmitting)
    }

    private func submit() async {
        guard let start else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        errorMessage = nil
        do {
            try await spaces.book(room, start: start, minutes: minutes, attendees: attendees, purpose: purpose, day: day)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
