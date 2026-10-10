using UnrealBuildTool;

public class ShunyaGameEditorTarget : TargetRules
{
    public ShunyaGameEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("ShunyaGame");
    }
}
