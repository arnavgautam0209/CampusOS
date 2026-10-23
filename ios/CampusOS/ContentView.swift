import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            NavigationStack { HomeView() }
                .tabItem { Label("Home", systemImage: "house.fill") }
            NavigationStack { MyBookingsView() }
                .tabItem { Label("Bookings", systemImage: "calendar") }
            NavigationStack { AIPlannerView() }
                .tabItem { Label("AI Planner", systemImage: "sparkles") }
            NavigationStack { ProfileView() }
                .tabItem { Label("Profile", systemImage: "person.fill") }
        }
        .tint(.indigo)
    }
}

#Preview {
    ContentView().environmentObject(BookingStore())
}
