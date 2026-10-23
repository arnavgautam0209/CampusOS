import SwiftUI

@main
struct CampusOSApp: App {
    @StateObject private var bookings = BookingStore()
    @StateObject private var auth = AuthManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(bookings)
                .environmentObject(auth)
        }
    }
}
