using UnrealBuildTool;

public class ShunyaGameTarget : TargetRules
{
    public ShunyaGameTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("ShunyaGame");
    }
}
