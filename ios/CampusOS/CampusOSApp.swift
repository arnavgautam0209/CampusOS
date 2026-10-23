import SwiftUI

@main
struct CampusOSApp: App {
    @StateObject private var auth: AuthManager
    @StateObject private var labs: LabStore
    @StateObject private var bookings: BookingStore
    @StateObject private var skillPass: SkillPassStore
    @StateObject private var attendance: AttendanceStore

    init() {
        let api = APIClient()
        _auth = StateObject(wrappedValue: AuthManager(api: api))
        _labs = StateObject(wrappedValue: LabStore(api: api))
        _bookings = StateObject(wrappedValue: BookingStore(service: APIBookingService(api: api)))
        _skillPass = StateObject(wrappedValue: SkillPassStore(service: APISkillPassService(api: api)))
        _attendance = StateObject(wrappedValue: AttendanceStore(service: APIAttendanceService(api: api)))
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(auth)
                .environmentObject(labs)
                .environmentObject(bookings)
                .environmentObject(skillPass)
                .environmentObject(attendance)
        }
    }
}
