import SwiftUI
struct ProfileView: View {
    var body: some View {
        ContentUnavailableView("Demo Student", systemImage: "person.crop.circle",
          description: Text("Sign-in and university role verification will be added with the backend."))
        .navigationTitle("Profile")
    }
}
