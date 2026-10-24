import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var bookings: BookingStore
    @EnvironmentObject private var skillPass: SkillPassStore
    @EnvironmentObject private var attendance: AttendanceStore
    @EnvironmentObject private var attendanceReports: AttendanceReportStore
    @EnvironmentObject private var planner: PlannerStore
    @EnvironmentObject private var inventory: InventoryStore
    @EnvironmentObject private var safeLab: SafeLabStore
    @EnvironmentObject private var spaces: SpacesStore
    @EnvironmentObject private var roomFinder: RoomFinderStore
    @EnvironmentObject private var timetables: TimetableStore
    @EnvironmentObject private var requests: RequestsStore
    @State private var tab = Tab.home

    enum Tab { case home, bookings, requests, planner, profile }

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack { HomeView() }
                .tabItem { Label("Home", systemImage: "house.fill") }
                .tag(Tab.home)

            NavigationStack { MyBookingsView() }
                .tabItem { Label("Bookings", systemImage: "calendar") }
                .tag(Tab.bookings)

            // Admins get the Admin Requests dashboard, students their own requests.
            NavigationStack { RequestsView() }
                .tabItem { Label("Requests", systemImage: "tray.full") }
                .tag(Tab.requests)
                .badge(auth.currentUser?.role.isStaff == true ? requests.requests.count : 0)

            NavigationStack { AIPlannerView() }
                .tabItem { Label("AI Planner", systemImage: "sparkles") }
                .tag(Tab.planner)

            NavigationStack { ProfileView() }
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
                .tag(Tab.profile)
        }
        .tint(.indigo)
        .onChange(of: auth.currentUser?.username) { old, new in
            // Right after an admin signs in, open their request dashboard.
            if old == nil, new != nil, auth.currentUser?.role.isStaff == true { tab = .requests }
        }
        .onChange(of: auth.isSignedIn) { _, signedIn in
            if !signedIn {
                requests.reset()
                bookings.reset()
                skillPass.reset()
                attendance.reset()
                attendanceReports.reset()
                planner.reset()
                inventory.reset()
                safeLab.reset()
                spaces.reset()
                roomFinder.reset()
                timetables.reset()
            }
        }
    }
}

#Preview {
    ContentView().previewEnvironment()
}
