import SwiftUI

struct HomeView: View {
    private let services: [(name: String, caption: String, icon: String)] = [
        ("LabOS", "Labs & equipment", "flask.fill"),
        ("AssetX", "Inventory & tools", "shippingbox.fill"),
        ("SafeLab", "Safety monitoring", "shield.fill"),
        ("SpacePulse", "Rooms & bookings", "building.2.fill"),
        ("SkillPass", "Skills & access", "checkmark.seal.fill"),
        ("ProxyGuard", "Attendance integrity", "person.crop.rectangle.stack")
    ]
    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Text("Welcome to CampusOS 👋")
                    .font(.largeTitle.bold())
                Text("Your entire campus, in one app.")
                    .foregroundStyle(.secondary)
                NavigationLink {
                    AIPlannerView()
                } label: {
                    HStack(spacing: 14) {
                        Image(systemName: "sparkles").font(.title)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Campus AI").font(.headline)
                            Text("Plan your next project").font(.subheadline)
                        }
                        Spacer()
                        Image(systemName: "arrow.right")
                    }
                    .padding()
                    .background(Color.indigo.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                .buttonStyle(.plain)

                Text("Campus Services").font(.title2.bold())
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(services, id: \.name) { item in
                        NavigationLink {
                            destination(for: item.name)
                        } label: {
                            ModuleCard(title: item.name, subtitle: item.caption, symbol: item.icon)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding()
        }
        .navigationTitle("CampusOS")
    }

    @ViewBuilder
    private func destination(for name: String) -> some View {
        switch name {
        case "LabOS": LabOSView()
        case "AssetX": AssetXView()
        case "SafeLab": SafeLabView()
        case "SpacePulse": SpacePulseView()
        case "SkillPass": SkillPassView()
        case "ProxyGuard": ProxyGuardView()
        default: Text("Coming soon")
        }
    }
}
