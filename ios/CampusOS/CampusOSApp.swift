import SwiftUI

@main
struct CampusOSApp: App {
    @StateObject private var store = BookingStore()
    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(store)
        }
    }
}
