import SwiftUI

struct HomeView: View {
    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Welcome to CampusOS 👋")
                        .font(.largeTitle.bold())
                    Text("Your entire campus, in one app.")
                        .foregroundStyle(.secondary)
                }

                NavigationLink {
                    AIPlannerView()
                } label: {
                    HStack(spacing: 14) {
                        Image(systemName: "sparkles")
                            .font(.title2)
                            .foregroundStyle(.purple)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Campus AI Planner").font(.headline)
                            Text("Tell us what you want to build")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "arrow.right")
                    }
                    .foregroundStyle(.primary)
                    .padding()
                    .background(Color.purple.opacity(0.10), in: RoundedRectangle(cornerRadius: 18))
                }

                Text("Campus Services").font(.title2.bold())

                LazyVGrid(columns: columns, spacing: 14) {
                    NavigationLink { LabOSView() } label: {
                        ModuleCard(title: "LabOS", subtitle: "Labs & equipment", symbol: "flask.fill", tint: .indigo)
                    }
                    NavigationLink { AssetXView() } label: {
                        ModuleCard(title: "AssetX", subtitle: "Inventory & tools", symbol: "shippingbox.fill", tint: .orange)
                    }
                    NavigationLink { SafeLabView() } label: {
                        ModuleCard(title: "SafeLab", subtitle: "Equipment faults", symbol: "wrench.and.screwdriver.fill", tint: .red)
                    }
                    NavigationLink { SpacePulseView() } label: {
                        ModuleCard(title: "SpacePulse", subtitle: "Rooms & bookings", symbol: "building.2.fill", tint: .teal)
                    }
                    NavigationLink { SkillPassView() } label: {
                        ModuleCard(title: "SkillPass", subtitle: "Skills & access", symbol: "checkmark.seal.fill", tint: .green)
                    }
                    NavigationLink { ProxyGuardView() } label: {
                        ModuleCard(title: "ProxyGuard", subtitle: "Attendance integrity", symbol: "person.crop.rectangle.stack.fill", tint: .purple)
                    }
                }
                .buttonStyle(.plain)
            }
            .padding()
        }
        .navigationTitle("CampusOS")
    }
}
