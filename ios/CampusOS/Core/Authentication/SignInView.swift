import SwiftUI

struct SignInView: View {
    /// Show a Cancel button when presented as a sheet.
    var showsCancel = false

    @EnvironmentObject private var auth: AuthManager
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var password = ""
    @State private var serverAddress = AppConfig.baseURL.absoluteString
    @State private var isSigningIn = false
    @State private var errorMessage: String?

    private var canSubmit: Bool {
        !username.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty && !isSigningIn
    }

    var body: some View {
        Form {
            Section {
                Label("Sign in to CampusOS", systemImage: "person.badge.key.fill")
                    .font(.headline)
                Text("Bookings are saved on the campus server, so everyone sees the same availability.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Section("Account") {
                TextField("Username", text: $username)
                    .textContentType(.username)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("Password", text: $password)
                    .textContentType(.password)
            }
            Section {
                TextField("Server address", text: $serverAddress)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            } header: {
                Text("Server")
            } footer: {
                Text("Simulator: http://127.0.0.1:8000/api/v1/. On an iPhone, use your Mac's Wi-Fi IP address, e.g. 192.168.1.20:8000.")
            }
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }
            Section {
                Button {
                    Task { await signIn() }
                } label: {
                    HStack {
                        Spacer()
                        if isSigningIn { ProgressView() } else { Text("Sign In").bold() }
                        Spacer()
                    }
                }
                .disabled(!canSubmit)
            }
        }
        .navigationTitle("Sign In")
        .toolbar {
            if showsCancel {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func signIn() async {
        guard AppConfig.setBaseURL(serverAddress) else {
            errorMessage = "Enter a valid server address, such as http://127.0.0.1:8000/api/v1/."
            return
        }
        serverAddress = AppConfig.baseURL.absoluteString
        errorMessage = nil
        isSigningIn = true
        defer { isSigningIn = false }
        do {
            try await auth.signIn(username: username.trimmingCharacters(in: .whitespaces),
                                  password: password)
            password = ""
            if showsCancel { dismiss() }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
