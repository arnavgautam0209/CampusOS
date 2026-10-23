import SwiftUI

/// Faculty see the live dashboard; students see their own attendance.
struct ProxyGuardView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var showingSignIn = false
    @State private var profileFailed = false

    var body: some View {
        content
            .navigationTitle("ProxyGuard")
            .sheet(isPresented: $showingSignIn) {
                NavigationStack { SignInView(showsCancel: true) }
            }
    }

    @ViewBuilder
    private var content: some View {
        if !auth.isSignedIn {
            ContentUnavailableView {
                Label("Sign In for Attendance", systemImage: "person.crop.rectangle.stack")
            } description: {
                Text("Students see their attendance here. Faculty see live card taps from classroom readers.")
            } actions: {
                Button("Sign In") { showingSignIn = true }
                    .buttonStyle(.borderedProminent)
            }
        } else if let user = auth.currentUser {
            if user.role.isStaff { LiveAttendanceView() } else { MyAttendanceView() }
        } else if profileFailed {
            ContentUnavailableView {
                Label("Can't Load Your Profile", systemImage: "wifi.exclamationmark")
            } description: {
                Text("Check that the CampusOS server is reachable.")
            } actions: {
                Button("Try Again") { Task { await loadProfile() } }
                    .buttonStyle(.borderedProminent)
            }
        } else {
            ProgressView("Loading your profile…")
                .task { await loadProfile() }
        }
    }

    private func loadProfile() async {
        profileFailed = false
        await auth.refreshProfile()
        profileFailed = auth.currentUser == nil
    }
}

/// "Live · updated 12:01:05" or a reconnecting warning, shown at the top of both screens.
struct LiveStatusRow: View {
    let lastUpdated: Date?
    let errorMessage: String?

    var body: some View {
        if let errorMessage, lastUpdated != nil {
            Label("Reconnecting… \(errorMessage)", systemImage: "wifi.exclamationmark")
                .font(.caption).foregroundStyle(.orange)
        } else if let lastUpdated {
            HStack(spacing: 8) {
                Circle().fill(.green).frame(width: 8, height: 8)
                Text("Live · updated \(lastUpdated.formatted(date: .omitted, time: .standard))")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
        }
    }
}
