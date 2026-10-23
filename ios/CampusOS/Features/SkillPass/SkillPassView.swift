import SwiftUI
struct SkillPassView: View {
    var body: some View {
        ContentUnavailableView("Skills & Permissions", systemImage: "checkmark.seal.fill",
            description: Text("Faculty-approved certifications will gate restricted equipment access."))
        .navigationTitle("SkillPass")
    }
}
