import SwiftUI

struct MyBookingsView: View {
    @EnvironmentObject private var store: BookingStore
    @EnvironmentObject private var auth: AuthManager
    @State private var showingSignIn = false
    @State private var cancellingID: UUID?
    @State private var cancelError: String?

    var body: some View {
        content
            .navigationTitle("My Bookings")
            .task(id: auth.isSignedIn) {
                guard auth.isSignedIn else { return store.reset() }
                await store.load()
                // Keep refreshing while this screen is open so a check-in tap at
                // the lab door shows up without pulling to refresh.
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(5))
                    if Task.isCancelled { break }
                    await store.refresh()
                }
            }
            .sheet(isPresented: $showingSignIn) {
                NavigationStack { SignInView(showsCancel: true) }
            }
            .alert("Couldn't Cancel", isPresented: Binding(
                get: { cancelError != nil }, set: { if !$0 { cancelError = nil } })
            ) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(cancelError ?? "")
            }
    }

    @ViewBuilder
    private var content: some View {
        let upcoming = store.upcoming
        if !auth.isSignedIn {
            ContentUnavailableView {
                Label("Sign In to See Bookings", systemImage: "person.badge.key")
            } description: {
                Text("Your reservations are stored on the CampusOS server.")
            } actions: {
                Button("Sign In") { showingSignIn = true }
                    .buttonStyle(.borderedProminent)
            }
        } else if upcoming.isEmpty, let message = store.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load Bookings", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await store.load() } }
                    .buttonStyle(.borderedProminent)
            }
        } else if upcoming.isEmpty, store.loadState != .loaded {
            ProgressView("Loading bookings…")
        } else if upcoming.isEmpty {
            ContentUnavailableView("No bookings yet", systemImage: "calendar.badge.clock",
                                   description: Text("Book a laboratory from LabOS to see it here."))
                .refreshable { await store.load() }
        } else {
            List {
                if let message = store.loadState.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                }
                ForEach(upcoming) { item in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(item.labName).font(.headline)
                        Label(item.start.formatted(date: .abbreviated, time: .shortened),
                              systemImage: "calendar")
                            .font(.subheadline).foregroundStyle(.secondary)
                        Text("Ends: \(item.end.formatted(date: .omitted, time: .shortened))")
                            .font(.caption).foregroundStyle(.secondary)
                        CheckInStatus(booking: item)
                        // Checked-in sessions can't be cancelled (the server refuses too).
                        if item.checkedInAt == nil {
                            if cancellingID == item.id {
                                ProgressView()
                            } else {
                                Button("Cancel Booking", role: .destructive) {
                                    Task { await cancel(item) }
                                }
                                .disabled(cancellingID != nil)
                            }
                        }
                    }
                    .padding(.vertical, 6)
                }
            }
            .refreshable { await store.load() }
        }
    }

    private func cancel(_ booking: LabBooking) async {
        cancellingID = booking.id
        defer { cancellingID = nil }
        do {
            try await store.cancel(booking)
        } catch {
            cancelError = error.localizedDescription
        }
    }
}

/// Where a booking stands at the lab door: upcoming, check-in open, or checked in.
private struct CheckInStatus: View {
    let booking: LabBooking

    var body: some View {
        // Re-evaluates every 30 s so "check-in open" appears on time.
        TimelineView(.periodic(from: .now, by: 30)) { context in
            switch booking.checkInState(now: context.date) {
            case .checkedIn(let at):
                let ongoing = context.date < booking.end
                Label(ongoing
                      ? "Checked in at \(at.formatted(date: .omitted, time: .shortened)) · in use until \(booking.end.formatted(date: .omitted, time: .shortened))"
                      : "Checked in at \(at.formatted(date: .omitted, time: .shortened))",
                      systemImage: "door.left.hand.open")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.green)
            case .checkInOpen:
                Label("Tap your card at the lab door to check in", systemImage: "wave.3.right")
                    .font(.subheadline)
                    .foregroundStyle(.orange)
            case .upcoming:
                EmptyView()
            }
        }
    }
}
