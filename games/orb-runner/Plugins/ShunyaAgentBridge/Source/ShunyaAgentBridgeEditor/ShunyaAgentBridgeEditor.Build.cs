using UnrealBuildTool;

public class ShunyaAgentBridgeEditor : ModuleRules
{
    public ShunyaAgentBridgeEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });

        PrivateDependencyModuleNames.AddRange(new string[] {
            "UnrealEd",
            "HTTPServer",
            "Json",
            "AssetRegistry",
            "ShunyaAgentBridge"
        });
    }
}
