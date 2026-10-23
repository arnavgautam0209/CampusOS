import Foundation
import Combine

@MainActor
final class AuthManager: ObservableObject {
    // Demo identity only; replace with backend-issued authentication.
    @Published var currentUser = CampusUser(
        id: "STU001", name: "Campus Student",
        email: "student@example.edu", role: .student
    )
}
