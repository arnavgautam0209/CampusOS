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
    @StateObject private var roomFinder: RoomFinderStore
    @StateObject private var timetables: TimetableStore
    @StateObject private var requests: RequestsStore

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
        _roomFinder = StateObject(wrappedValue: RoomFinderStore(service: APISpacesService(api: api)))
        _timetables = StateObject(wrappedValue: TimetableStore(service: APISpacesService(api: api)))
        _requests = StateObject(wrappedValue: RequestsStore(service: APIRequestsService(api: api)))
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
                .environmentObject(roomFinder)
                .environmentObject(timetables)
                .environmentObject(requests)
        }
    }
}
