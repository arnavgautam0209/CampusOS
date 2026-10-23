import Foundation
import Combine

@MainActor
final class AuthManager: ObservableObject {
    @Published var demoRole = "student"
    // Future: Django authentication, secure token storage, server permissions.
}
