import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var auth: AuthManager

    var body: some View {
        Form {
            Section {
                HStack(spacing: 12) {
                    Image(systemName: "person.crop.circle.fill")
                        .font(.system(size: 48)).foregroundStyle(.indigo)
                    VStack(alignment: .leading) {
                        Text(auth.currentUser.name).font(.headline)
                        Text(auth.currentUser.email).font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            Section("Account") {
                LabeledContent("Student ID", value: auth.currentUser.id)
                LabeledContent("Role", value: auth.currentUser.role.rawValue.capitalized)
            }
            Section {
                Text("Demo profile. Backend authentication will replace this sample identity.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Profile")
    }
}
