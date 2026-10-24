import XCTest

/// Taps through the real app against a local backend and screenshots each screen.
///
/// Run it with `scripts/walkthrough.sh`, which seeds demo users and data, starts the
/// backend, passes the demo password and exports the screenshots. Without that
/// password (for example during a normal ⌘U run) the test is skipped.
final class WalkthroughUITests: XCTestCase {
    private static let serverAddress = "http://127.0.0.1:8000/api/v1/"
    private let app = XCUIApplication()
    private var step = 0

    override func setUp() {
        continueAfterFailure = true
    }

    func testWalkthrough() throws {
        let password = ProcessInfo.processInfo.environment["UI_PASSWORD"] ?? ""
        try XCTSkipIf(password.isEmpty, "Run scripts/walkthrough.sh to seed demo data and run the walkthrough.")
        app.launch()
        signOutIfNeeded()

        // Signed out home
        tab("Home")
        waitFor("Campus Services")
        shot("home")
        app.swipeUp()
        shot("home-services")

        // Sign in as the student
        tab("Profile")
        waitFor("Sign in to CampusOS")
        shot("sign-in")
        signIn("demo_ui_student", password)
        waitFor("Aarav Mehta", timeout: 15)
        shot("profile-student")

        // LabOS
        tab("Home")
        openCard("LabOS")
        waitFor("Explore Laboratories")
        shot("labos-list")
        tapButton("Robotics Lab")
        waitFor("Equipment")
        shot("lab-robotics")
        app.swipeUp()
        shot("lab-robotics-equipment")
        back()
        tapButton("Electronics Lab")
        waitFor("SkillPass Requirements")
        shot("lab-electronics-requirements")
        tapButton("Reserve Laboratory")
        waitFor("Reservation details")
        shot("reserve-form")
        back()
        back()
        back()

        // SkillPass
        openCard("SkillPass")
        waitFor("Your Certifications")
        shot("skillpass")
        back()

        // AssetX
        openCard("AssetX")
        waitFor("Borrowed by You", timeout: 15)
        shot("assetx")
        app.swipeUp()
        shot("assetx-inventory")
        back()

        // SafeLab
        openCard("SafeLab")
        waitFor("AI & Computing Lab", timeout: 15)
        shot("safelab")
        back()

        // Bookings tab
        tab("Bookings")
        waitFor("AI & Computing Lab")
        shot("bookings")

        // AI Planner
        tab("AI Planner")
        tapButton("Try the robot example")
        shot("planner-input")
        tapButton("Plan My Project")
        waitFor("What I Understood", timeout: 30)
        app.swipeUp()
        shot("planner-understood")
        app.swipeUp()
        shot("planner-recommendation")
        app.swipeUp()
        shot("planner-slots")
        app.swipeUp()
        app.swipeUp()
        shot("planner-next-steps")

        // ProxyGuard as the student
        tab("Home")
        app.swipeUp()
        openCard("ProxyGuard")
        waitFor("My Attendance", timeout: 15)
        shot("proxyguard-student")
        back()

        // Faculty view (the demo session is first: DEMO-ROOM sorts before real rooms)
        tab("Profile")
        tapButton("Sign Out")
        signIn("demo_ui_faculty", password)
        waitFor("Meera Iyer", timeout: 15)
        tab("Home")
        app.swipeUp()
        openCard("ProxyGuard")
        waitFor("Live Scan Feed", timeout: 15)
        shot("proxyguard-faculty")
        app.swipeUp()
        shot("proxyguard-faculty-feed")
        app.swipeUp()
        shot("proxyguard-faculty-readers")
        app.swipeDown()
        app.swipeDown()
        app.swipeDown()
        tapButton("Close Session")
        sleep(1)
        shot("proxyguard-close-confirm")
        // Leave the session open: dismiss the dialog without confirming.
        app.swipeDown()
    }

    // MARK: Helpers

    private func shot(_ name: String) {
        sleep(1)  // let animations and the 3-second live refresh settle
        step += 1
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = String(format: "%02d-%@", step, name)
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func predicate(_ text: String) -> NSPredicate {
        NSPredicate(format: "label CONTAINS[c] %@", text)
    }

    @discardableResult
    private func waitFor(_ text: String, timeout: TimeInterval = 10) -> Bool {
        let found = app.descendants(matching: .any).matching(predicate(text)).firstMatch
            .waitForExistence(timeout: timeout)
        XCTAssertTrue(found, "Didn't find \"\(text)\"")
        return found
    }

    private func tapButton(_ text: String) {
        let button = app.buttons.matching(predicate(text)).firstMatch
        guard button.waitForExistence(timeout: 10) else {
            XCTFail("No button \"\(text)\"")
            return
        }
        button.tap()
    }

    private func openCard(_ title: String) {
        // Home keeps its scroll position between visits, so start from the top.
        app.swipeDown()
        app.swipeDown()
        for _ in 0..<3 {
            let card = app.buttons.matching(predicate(title)).firstMatch
            if card.waitForExistence(timeout: 3), card.isHittable {
                card.tap()
                return
            }
            app.swipeUp()
        }
        XCTFail("No card \"\(title)\"")
    }

    private func tab(_ name: String) {
        let tabButton = app.tabBars.buttons[name].exists ? app.tabBars.buttons[name] : app.buttons[name].firstMatch
        guard tabButton.waitForExistence(timeout: 5) else { return XCTFail("No tab \(name)") }
        // Right after sign-in a tap can be swallowed while the keyboard and
        // password sheet animate away, so confirm the tab actually switched.
        for _ in 0..<4 where !tabButton.isSelected {
            tabButton.tap()
            sleep(1)
        }
    }

    private func back() {
        let button = app.navigationBars.buttons.element(boundBy: 0)
        if button.waitForExistence(timeout: 5) { button.tap() }
    }

    private func signOutIfNeeded() {
        tab("Profile")
        let signOut = app.buttons["Sign Out"]
        if signOut.waitForExistence(timeout: 4) { signOut.tap() }
    }

    private func signIn(_ username: String, _ password: String) {
        let user = app.textFields["Username"]
        XCTAssertTrue(user.waitForExistence(timeout: 10))
        user.tap()
        user.typeText(username)
        let secure = app.secureTextFields["Password"]
        secure.tap()
        secure.typeText(password)
        // The app remembers the last server; point it at the local walkthrough backend.
        let server = app.textFields["Server address"]
        if server.exists, (server.value as? String) != Self.serverAddress {
            server.tap()
            let current = (server.value as? String) ?? ""
            server.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count + 5))
            server.typeText(Self.serverAddress)
        }
        app.buttons.matching(NSPredicate(format: "label == 'Sign In'")).firstMatch.tap()
        dismissSavePassword()
    }

    /// iOS offers to save the password after signing in; decline so it doesn't cover the screens.
    private func dismissSavePassword() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for _ in 0..<6 {
            for owner in [app, springboard] {
                let notNow = owner.buttons["Not Now"]
                if notNow.exists {
                    notNow.tap()
                    return
                }
            }
            sleep(1)
        }
    }
}
