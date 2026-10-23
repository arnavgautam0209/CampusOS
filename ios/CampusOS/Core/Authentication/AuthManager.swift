import Foundation
import Combine

/// Signs in against Django token auth and keeps the token in the Keychain.
@MainActor
final class AuthManager: ObservableObject {
    @Published private(set) var isSignedIn: Bool
    @Published private(set) var currentUser: CampusUser?

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
        isSignedIn = api.tokenStore.readToken() != nil
        api.onUnauthorized = { [weak self] in self?.signOut() }
    }

    func signIn(username: String, password: String) async throws {
        struct Credentials: Encodable { let username: String; let password: String }
        struct TokenResponse: Decodable { let token: String }

        let response: TokenResponse = try await api.post(
            "auth/token/", body: Credentials(username: username, password: password), authenticated: false)
        try api.tokenStore.saveToken(response.token)
        isSignedIn = true
        await refreshProfile()
    }

    func refreshProfile() async {
        guard isSignedIn else { return }
        currentUser = try? await api.get("auth/me/", authenticated: true)
    }

    /// Forgets the token on this device. (The server token stays valid until an admin revokes it.)
    func signOut() {
        api.tokenStore.deleteToken()
        currentUser = nil
        isSignedIn = false
    }
}
