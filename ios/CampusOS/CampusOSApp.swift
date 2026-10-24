import SwiftUI

@main
struct CampusOSApp: App {
    @StateObject private var auth: AuthManager
    @StateObject private var labs: LabStore
    @StateObject private var bookings: BookingStore
    @StateObject private var skillPass: SkillPassStore
    @StateObject private var attendance: AttendanceStore
    @StateObject private var attendanceReports: AttendanceReportStore
    @StateObject private var planner: PlannerStore
    @StateObject private var inventory: InventoryStore
    @StateObject private var safeLab: SafeLabStore
    @StateObject private var spaces: SpacesStore

    init() {
        let api = APIClient()
        _auth = StateObject(wrappedValue: AuthManager(api: api))
        _labs = StateObject(wrappedValue: LabStore(api: api))
        _bookings = StateObject(wrappedValue: BookingStore(service: APIBookingService(api: api)))
        _skillPass = StateObject(wrappedValue: SkillPassStore(service: APISkillPassService(api: api)))
        _attendance = StateObject(wrappedValue: AttendanceStore(service: APIAttendanceService(api: api)))
        _attendanceReports = StateObject(wrappedValue: AttendanceReportStore(service: APIAttendanceService(api: api)))
        _planner = StateObject(wrappedValue: PlannerStore(service: APIPlannerService(api: api)))
        _inventory = StateObject(wrappedValue: InventoryStore(service: APIInventoryService(api: api)))
        _safeLab = StateObject(wrappedValue: SafeLabStore(service: APISafeLabService(api: api)))
        _spaces = StateObject(wrappedValue: SpacesStore(service: APISpacesService(api: api)))
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(auth)
                .environmentObject(labs)
                .environmentObject(bookings)
                .environmentObject(skillPass)
                .environmentObject(attendance)
                .environmentObject(attendanceReports)
                .environmentObject(planner)
                .environmentObject(inventory)
                .environmentObject(safeLab)
                .environmentObject(spaces)
        }
    }
}
