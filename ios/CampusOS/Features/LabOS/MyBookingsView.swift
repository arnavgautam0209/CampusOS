import SwiftUI

struct MyBookingsView: View {
    @EnvironmentObject private var store: BookingStore
    @EnvironmentObject private var auth: AuthManager
    @State private var showingSignIn = false
    @State private var cancellingID: UUID?
    @State private var errorMessage: String?
    @State private var declining: LabBooking?
    @State private var declineReason = ""

    private var isStaff: Bool { auth.currentUser?.role.isStaff == true }

    var body: some View {
        content
            .navigationTitle("My Bookings")
            .task(id: "\(auth.isSignedIn)-\(isStaff)") {
                guard auth.isSignedIn else { return store.reset() }
                await store.load()
                if isStaff { await store.loadReviews() }
                // Keep refreshing while this screen is open so a check-in tap at the
                // lab door or a faculty decision shows up without pulling to refresh.
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(5))
                    if Task.isCancelled { break }
                    await store.refresh()
                    if isStaff { await store.loadReviews() }
                }
            }
            .sheet(isPresented: $showingSignIn) {
                NavigationStack { SignInView(showsCancel: true) }
            }
            .alert("Decline Request", isPresented: Binding(
                get: { declining != nil }, set: { if !$0 { declining = nil } }),
                   presenting: declining
            ) { booking in
                TextField("Reason for the student", text: $declineReason)
                Button("Decline", role: .destructive) {
                    let reason = declineReason
                    Task { await act { try await store.decline(booking, note: reason) } }
                }
                Button("Cancel", role: .cancel) {}
            } message: { booking in
                Text("\(booking.student ?? "The student") won't be able to use \(booking.labName) at that time.")
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
        let upcoming = store.upcoming
        let notApproved = store.notApproved
        let nothing = upcoming.isEmpty && notApproved.isEmpty && !(isStaff && !store.pendingReviews.isEmpty)
        if !auth.isSignedIn {
            ContentUnavailableView {
                Label("Sign In to See Bookings", systemImage: "person.badge.key")
            } description: {
                Text("Your reservations are stored on the CampusOS server.")
            } actions: {
                Button("Sign In") { showingSignIn = true }
                    .buttonStyle(.borderedProminent)
            }
        } else if nothing, let message = store.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load Bookings", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await store.load() } }
                    .buttonStyle(.borderedProminent)
            }
        } else if nothing, store.loadState != .loaded {
            ProgressView("Loading bookings…")
        } else if nothing {
            ContentUnavailableView("No bookings yet", systemImage: "calendar.badge.clock",
                                   description: Text("Book a laboratory from LabOS to see it here."))
                .refreshable { await reload() }
        } else {
            List {
                if let message = store.loadState.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                }
                if isStaff {
                    reviewSection
                }
                if !upcoming.isEmpty {
                    Section("Upcoming") {
                        ForEach(upcoming) { bookingRow($0) }
                    }
                }
                if !notApproved.isEmpty {
                    Section("Not Approved") {
                        ForEach(notApproved) { booking in
                            VStack(alignment: .leading, spacing: 6) {
                                BookingHeader(booking: booking)
                                Label(booking.status == .expired
                                      ? "Not approved before the start time"
                                      : "Declined by \(booking.decidedBy ?? "faculty")",
                                      systemImage: "xmark.circle.fill")
                                    .font(.subheadline.weight(.semibold)).foregroundStyle(.red)
                                if let note = booking.decisionNote, !note.isEmpty {
                                    Text("“\(note)”").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
            .refreshable { await reload() }
        }
    }

    private var reviewSection: some View {
        Section {
            if store.pendingReviews.isEmpty {
                Text(store.reviewState.errorMessage ?? "No lab requests waiting.").foregroundStyle(.secondary)
            }
            ForEach(store.pendingReviews) { request in
                VStack(alignment: .leading, spacing: 6) {
                    Text(request.student ?? request.username ?? "Student").font(.headline)
                    BookingHeader(booking: request)
                    if let purpose = request.purpose, !purpose.isEmpty {
                        Text("“\(purpose)”").font(.caption).foregroundStyle(.secondary)
                    }
                    if request.username != nil, request.username == auth.currentUser?.username {
                        Text("Your request: another faculty member must approve it.")
                            .font(.caption).foregroundStyle(.secondary)
                    } else if store.reviewingID == request.id {
                        ProgressView()
                    } else {
                        HStack(spacing: 12) {
                            Button("Approve") { Task { await act { try await store.approve(request) } } }
                                .buttonStyle(.borderedProminent)
                                .tint(.green)
                            Button("Decline", role: .destructive) {
                                declineReason = ""
                                declining = request
                            }
                            .buttonStyle(.bordered)
                        }
                        .disabled(store.reviewingID != nil)
                    }
                }
                .padding(.vertical, 4)
            }
        } header: {
            HStack {
                Text("Lab Requests to Review")
                if !store.pendingReviews.isEmpty {
                    StatusBadge(text: "\(store.pendingReviews.count)", color: .orange)
                }
            }
        } footer: {
            Text("Approving confirms the booking under your name. CampusOS re-checks the student's SkillPass certifications first.")
        }
    }

    private func bookingRow(_ item: LabBooking) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            BookingHeader(booking: item)
            if item.status == .pending {
                Label("Waiting for faculty approval", systemImage: "hourglass")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(.orange)
            } else {
                if let decidedBy = item.decidedBy {
                    Label("Approved by \(decidedBy)", systemImage: "checkmark.seal.fill")
                        .font(.caption).foregroundStyle(.green)
                    if let note = item.decisionNote, !note.isEmpty {
                        Text("“\(note)”").font(.caption).foregroundStyle(.secondary)
                    }
                }
                CheckInStatus(booking: item)
            }
            // Checked-in sessions can't be cancelled (the server refuses too).
            if item.checkedInAt == nil {
                if cancellingID == item.id {
                    ProgressView()
                } else {
                    Button(item.status == .pending ? "Withdraw Request" : "Cancel Booking", role: .destructive) {
                        Task { await cancel(item) }
                    }
                    .disabled(cancellingID != nil)
                }
            }
        }
        .padding(.vertical, 6)
    }

    private func reload() async {
        await store.load()
        if isStaff { await store.loadReviews() }
    }

    private func cancel(_ booking: LabBooking) async {
        cancellingID = booking.id
        defer { cancellingID = nil }
        await act { try await store.cancel(booking) }
    }

    private func act(_ action: () async throws -> Void) async {
        do {
            try await action()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct BookingHeader: View {
    let booking: LabBooking

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(booking.labName).font(.headline)
            Label("\(booking.start.formatted(date: .abbreviated, time: .shortened))–\(booking.end.formatted(date: .omitted, time: .shortened))",
                  systemImage: "calendar")
                .font(.subheadline).foregroundStyle(.secondary)
        }
    }
}

/// Where a confirmed booking stands at the lab door: upcoming, check-in open, or checked in.
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
