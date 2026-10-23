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
                if auth.isSignedIn { await store.load() } else { store.reset() }
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
                        if cancellingID == item.id {
                            ProgressView()
                        } else {
                            Button("Cancel Booking", role: .destructive) {
                                Task { await cancel(item) }
                            }
                            .disabled(cancellingID != nil)
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
