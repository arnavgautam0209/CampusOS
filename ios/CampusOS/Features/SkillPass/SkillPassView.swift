import SwiftUI

struct SkillPassView: View {
    @EnvironmentObject private var skillPass: SkillPassStore
    @EnvironmentObject private var auth: AuthManager
    @State private var showingSignIn = false

    var body: some View {
        content
            .navigationTitle("SkillPass")
            .task(id: auth.isSignedIn) { await skillPass.loadIfNeeded(signedIn: auth.isSignedIn) }
            .sheet(isPresented: $showingSignIn) {
                NavigationStack { SignInView(showsCancel: true) }
            }
    }

    @ViewBuilder
    private var content: some View {
        if skillPass.catalog.isEmpty, let message = skillPass.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load SkillPass", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await skillPass.load(signedIn: auth.isSignedIn) } }
                    .buttonStyle(.borderedProminent)
            }
        } else if skillPass.catalog.isEmpty, skillPass.loadState != .loaded {
            ProgressView("Loading certifications…")
        } else {
            list
        }
    }

    private var list: some View {
        let held = skillPass.catalog.filter { skillPass.standing(for: $0.id) != .notRequested }
        let available = skillPass.catalog.filter { skillPass.standing(for: $0.id) == .notRequested }

        return List {
            if let message = skillPass.loadState.errorMessage {
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
            }
            if !auth.isSignedIn {
                Section {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Sign in to see your certifications and request training.")
                            .foregroundStyle(.secondary)
                        Button("Sign In") { showingSignIn = true }
                            .buttonStyle(.borderedProminent)
                    }
                    .padding(.vertical, 4)
                }
            } else if !held.isEmpty {
                Section("Your Certifications") {
                    ForEach(held) { CertificationRow(certification: $0) }
                }
            }
            Section {
                ForEach(auth.isSignedIn ? available : skillPass.catalog) { CertificationRow(certification: $0) }
            } header: {
                Text(auth.isSignedIn ? "Available Training" : "Certifications")
            } footer: {
                Text("Restricted labs need these certifications before you can book them. Only faculty can approve a certification; CampusOS AI never grants one.")
            }
        }
        .refreshable { await skillPass.load(signedIn: auth.isSignedIn) }
    }
}
