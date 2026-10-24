import SwiftUI

/// Admins see every pending lab and equipment request; students see their own requests and decisions.
struct RequestsView: View {
    @EnvironmentObject private var store: RequestsStore
    @EnvironmentObject private var auth: AuthManager
    @State private var rejecting: CampusRequest?
    @State private var reason = ""
    @State private var errorMessage: String?
    @State private var showingSignIn = false

    private var isAdmin: Bool { auth.currentUser?.role.isStaff == true }

    var body: some View {
        content
            .navigationTitle(isAdmin ? "Admin Requests" : "My Requests")
            .task(id: "\(auth.isSignedIn)-\(isAdmin)") {
                guard auth.isSignedIn else { return store.reset() }
                while !Task.isCancelled {
                    await store.load()
                    try? await Task.sleep(for: .seconds(5))
                }
            }
            .refreshable { await store.load() }
            .sheet(isPresented: $showingSignIn) { NavigationStack { SignInView(showsCancel: true) } }
            .alert("Reject Request", isPresented: Binding(get: { rejecting != nil }, set: { if !$0 { rejecting = nil } }),
                   presenting: rejecting) { request in
                TextField("Reason (optional)", text: $reason)
                Button("Reject", role: .destructive) {
                    let note = reason
                    Task { await act { try await store.reject(request, note: note) } }
                }
                Button("Cancel", role: .cancel) {}
            } message: { request in
                Text("\(request.requester) will see this on their request for \(request.title).")
            }
            .alert("Couldn't Update Request", isPresented: Binding(
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
                Label("Sign In to See Requests", systemImage: "tray.full")
            } description: {
                Text("Lab booking and equipment requests appear here.")
            } actions: {
                Button("Sign In") { showingSignIn = true }.buttonStyle(.borderedProminent)
            }
        } else if store.requests.isEmpty, let message = store.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load Requests", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await store.load() } }.buttonStyle(.borderedProminent)
            }
        } else if store.requests.isEmpty, store.loadState != .loaded {
            ProgressView("Loading requests…")
        } else if store.requests.isEmpty {
            ContentUnavailableView(isAdmin ? "No Pending Requests" : "No Requests Yet", systemImage: "tray",
                                   description: Text(isAdmin
                                                     ? "New lab booking and equipment requests from students appear here."
                                                     : "Request a lab in LabOS or equipment in AssetX."))
        } else {
            List {
                let labs = store.requests.filter { $0.type == .labBooking }
                let equipment = store.requests.filter { $0.type == .equipment }
                if !labs.isEmpty {
                    Section("Lab Bookings (LabOS)") { ForEach(labs) { row($0) } }
                }
                if !equipment.isEmpty {
                    Section("Equipment (AssetX)") { ForEach(equipment) { row($0) } }
                }
            }
        }
    }

    private func row(_ request: CampusRequest) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                Image(systemName: request.type == .labBooking ? "flask" : "shippingbox")
                    .foregroundStyle(.indigo)
                VStack(alignment: .leading, spacing: 2) {
                    Text(request.title).font(.headline)
                    Text(request.detail).font(.subheadline).foregroundStyle(.secondary)
                    if isAdmin {
                        Text(request.requester).font(.subheadline)
                    }
                    if !request.purpose.isEmpty {
                        Text("“\(request.purpose)”").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                StatusBadge(text: label(request.status), color: color(request.status))
            }
            if let decidedBy = request.decidedBy, request.status != .pending {
                Text("\(request.status == .rejected ? "Rejected" : "Decided") by \(decidedBy)"
                     + (request.decisionNote.isEmpty ? "" : ": “\(request.decisionNote)”"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if isAdmin, request.status == .pending {
                if store.decidingID == request.id {
                    ProgressView()
                } else if request.username == auth.currentUser?.username {
                    Text("Your own request: another admin must decide it.").font(.caption).foregroundStyle(.secondary)
                } else {
                    HStack(spacing: 12) {
                        Button("Approve") { Task { await act { try await store.approve(request) } } }
                            .buttonStyle(.borderedProminent).tint(.green)
                        Button("Reject", role: .destructive) {
                            reason = ""
                            rejecting = request
                        }
                        .buttonStyle(.bordered)
                    }
                    .disabled(store.decidingID != nil)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func label(_ status: CampusRequest.Status) -> String {
        switch status {
        case .pending: return "Pending"
        case .approved: return "Approved"
        case .rejected: return "Rejected"
        case .cancelled: return "Cancelled"
        case .expired: return "Expired"
        case .returned: return "Returned"
        case .other: return "Updated"
        }
    }

    private func color(_ status: CampusRequest.Status) -> Color {
        switch status {
        case .pending: return .orange
        case .approved: return .green
        case .rejected, .expired: return .red
        default: return .secondary
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
