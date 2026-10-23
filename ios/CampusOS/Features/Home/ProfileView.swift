import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var auth: AuthManager

    var body: some View {
        Group {
            if auth.isSignedIn {
                profile
            } else {
                SignInView()
            }
        }
        .navigationTitle("Profile")
    }

    private var profile: some View {
        Form {
            Section {
                HStack(spacing: 12) {
                    Image(systemName: "person.crop.circle.fill")
                        .font(.system(size: 48)).foregroundStyle(.indigo)
                    VStack(alignment: .leading) {
                        if let user = auth.currentUser {
                            Text(user.name).font(.headline)
                            if !user.email.isEmpty {
                                Text(user.email).font(.caption).foregroundStyle(.secondary)
                            }
                        } else {
                            ProgressView()
                        }
                    }
                }
            }
            if let user = auth.currentUser {
                Section("Account") {
                    LabeledContent("User ID", value: user.id)
                    LabeledContent("Role", value: user.role.rawValue.capitalized)
                }
            }
            Section("Server") {
                LabeledContent("Connected to", value: AppConfig.baseURL.absoluteString)
            }
            Section {
                Button("Sign Out", role: .destructive) { auth.signOut() }
            }
        }
        .task {
            if auth.currentUser == nil { await auth.refreshProfile() }
        }
    }
}
