import SwiftUI
struct AssetXView: View {
    var body: some View {
        ContentUnavailableView("Inventory and Tool Tracking", systemImage: "shippingbox.fill",
            description: Text("Browse, checkout and return equipment. Demo data only."))
        .navigationTitle("AssetX")
    }
}
