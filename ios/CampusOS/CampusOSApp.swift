import SwiftUI

@main
struct CampusOSApp: App {
    @StateObject private var auth: AuthManager
    @StateObject private var labs: LabStore
    @StateObject private var bookings: BookingStore

    init() {
        let api = APIClient()
        _auth = StateObject(wrappedValue: AuthManager(api: api))
        _labs = StateObject(wrappedValue: LabStore(api: api))
        _bookings = StateObject(wrappedValue: BookingStore(service: APIBookingService(api: api)))
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(auth)
                .environmentObject(labs)
                .environmentObject(bookings)
        }
    }
}
