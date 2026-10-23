import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var bookings: BookingStore
    @EnvironmentObject private var skillPass: SkillPassStore

    var body: some View {
        TabView {
            NavigationStack { HomeView() }
                .tabItem { Label("Home", systemImage: "house.fill") }

            NavigationStack { MyBookingsView() }
                .tabItem { Label("Bookings", systemImage: "calendar") }

            NavigationStack { AIPlannerView() }
                .tabItem { Label("AI Planner", systemImage: "sparkles") }

            NavigationStack { ProfileView() }
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
        }
        .tint(.indigo)
        .onChange(of: auth.isSignedIn) { _, signedIn in
            if !signedIn {
                bookings.reset()
                skillPass.reset()
            }
        }
    }
}

#Preview {
    ContentView().previewEnvironment()
}
