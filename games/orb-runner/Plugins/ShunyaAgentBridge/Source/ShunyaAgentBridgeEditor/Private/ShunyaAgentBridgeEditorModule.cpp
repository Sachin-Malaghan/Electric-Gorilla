// Shunya Agent Bridge - editor HTTP endpoint (spec 17, 18).
//
// A small, whitelisted surface for the studio backend:
//   GET  /shunya/status | level | actors | actor | assets | telemetry     (scope: read)
//   POST /shunya/command {command, args}                                   (scope: editor | runtime)
//
// Safety: localhost only, shared-secret token, an explicit command whitelist, separate
// editor / runtime scopes, edits wrapped in undoable transactions. There is no generic
// "execute" route and no arbitrary memory or console access.

#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Dom/JsonObject.h"
#include "Editor.h"
#include "Engine/Level.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FileHelpers.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HttpPath.h"
#include "HttpServerModule.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "Misc/App.h"
#include "Misc/EngineVersion.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "PlayInEditorDataTypes.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "ShunyaBridgeSettings.h"
#include "ShunyaTelemetrySubsystem.h"
#include "UnrealClient.h"

DEFINE_LOG_CATEGORY_STATIC(LogShunyaBridge, Log, All);

namespace ShunyaBridge
{
	using FJson = TSharedRef<FJsonObject>;

	FJson MakeJson()
	{
		return MakeShared<FJsonObject>();
	}

	TUniquePtr<FHttpServerResponse> Respond(const FJson& Json, EHttpServerResponseCodes Code = EHttpServerResponseCodes::Ok)
	{
		FString Body;
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
		FJsonSerializer::Serialize(Json, Writer);
		TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(Body, TEXT("application/json"));
		Response->Code = Code;
		return Response;
	}

	TUniquePtr<FHttpServerResponse> Fail(EHttpServerResponseCodes Code, const FString& Message)
	{
		FJson Json = MakeJson();
		Json->SetBoolField(TEXT("ok"), false);
		Json->SetStringField(TEXT("error"), Message);
		return Respond(Json, Code);
	}

	FString Header(const FHttpServerRequest& Request, const FString& Name)
	{
		for (const TPair<FString, TArray<FString>>& Pair : Request.Headers)
		{
			if (Pair.Key.Equals(Name, ESearchCase::IgnoreCase) && Pair.Value.Num() > 0)
			{
				return Pair.Value[0];
			}
		}
		return FString();
	}

	FString Query(const FHttpServerRequest& Request, const TCHAR* Name, const FString& Default = FString())
	{
		const FString* Value = Request.QueryParams.Find(Name);
		return Value ? *Value : Default;
	}

	bool Authorized(const FHttpServerRequest& Request)
	{
		const UShunyaBridgeSettings* Settings = GetDefault<UShunyaBridgeSettings>();
		return !Settings->Token.IsEmpty() && Header(Request, TEXT("X-Shunya-Token")).Equals(Settings->Token, ESearchCase::CaseSensitive);
	}

	UWorld* EditorWorld()
	{
		return GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	}

	UWorld* PlayWorld()
	{
		return GEditor ? GEditor->PlayWorld.Get() : nullptr;
	}

	AActor* FindActor(UWorld* World, const FString& Name)
	{
		if (!World || Name.IsEmpty())
		{
			return nullptr;
		}
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			if (It->GetActorLabel().Equals(Name, ESearchCase::IgnoreCase) || It->GetName().Equals(Name, ESearchCase::IgnoreCase))
			{
				return *It;
			}
		}
		return nullptr;
	}

	FJson VectorJson(const FVector& V)
	{
		FJson Json = MakeJson();
		Json->SetNumberField(TEXT("x"), V.X);
		Json->SetNumberField(TEXT("y"), V.Y);
		Json->SetNumberField(TEXT("z"), V.Z);
		return Json;
	}

	FJson ActorSummary(const AActor* Actor)
	{
		FJson Json = MakeJson();
		Json->SetStringField(TEXT("name"), Actor->GetName());
		Json->SetStringField(TEXT("label"), Actor->GetActorLabel());
		Json->SetStringField(TEXT("class"), Actor->GetClass()->GetName());
		Json->SetObjectField(TEXT("location"), VectorJson(Actor->GetActorLocation()));
		return Json;
	}

	// ------------------------------------------------------------------ read routes

	TUniquePtr<FHttpServerResponse> Status(const FHttpServerRequest&)
	{
		FJson Json = MakeJson();
		Json->SetBoolField(TEXT("ok"), true);
		Json->SetStringField(TEXT("engine"), FEngineVersion::Current().ToString());
		Json->SetStringField(TEXT("project"), FApp::GetProjectName());
		Json->SetStringField(TEXT("project_dir"), FPaths::ConvertRelativePathToFull(FPaths::ProjectDir()));
		Json->SetBoolField(TEXT("pie"), PlayWorld() != nullptr);
		if (const UWorld* World = EditorWorld())
		{
			Json->SetStringField(TEXT("level"), World->GetMapName());
		}
		return Respond(Json);
	}

	TUniquePtr<FHttpServerResponse> Level(const FHttpServerRequest&)
	{
		UWorld* World = EditorWorld();
		if (!World)
		{
			return Fail(EHttpServerResponseCodes::NotFound, TEXT("no editor world"));
		}
		TMap<FString, int32> Counts;
		int32 Total = 0;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			Counts.FindOrAdd(It->GetClass()->GetName())++;
			++Total;
		}
		FJson ByClass = MakeJson();
		for (const TPair<FString, int32>& Pair : Counts)
		{
			ByClass->SetNumberField(Pair.Key, Pair.Value);
		}
		FJson Json = MakeJson();
		Json->SetBoolField(TEXT("ok"), true);
		Json->SetStringField(TEXT("name"), World->GetMapName());
		Json->SetStringField(TEXT("path"), World->GetOutermost()->GetName());
		Json->SetNumberField(TEXT("actor_count"), Total);
		Json->SetObjectField(TEXT("actors_by_class"), ByClass);
		return Respond(Json);
	}

	TUniquePtr<FHttpServerResponse> Actors(const FHttpServerRequest& Request)
	{
		UWorld* World = EditorWorld();
		if (!World)
		{
			return Fail(EHttpServerResponseCodes::NotFound, TEXT("no editor world"));
		}
		const FString NameFilter = Query(Request, TEXT("name"));
		const FString ClassFilter = Query(Request, TEXT("class_name"));
		const int32 Limit = FMath::Clamp(FCString::Atoi(*Query(Request, TEXT("limit"), TEXT("50"))), 1, 500);
		TArray<TSharedPtr<FJsonValue>> Items;
		for (TActorIterator<AActor> It(World); It && Items.Num() < Limit; ++It)
		{
			if (!NameFilter.IsEmpty() && !It->GetActorLabel().Contains(NameFilter) && !It->GetName().Contains(NameFilter))
			{
				continue;
			}
			if (!ClassFilter.IsEmpty() && !It->GetClass()->GetName().Contains(ClassFilter))
			{
				continue;
			}
			Items.Add(MakeShared<FJsonValueObject>(ActorSummary(*It)));
		}
		FJson Json = MakeJson();
		Json->SetBoolField(TEXT("ok"), true);
		Json->SetArrayField(TEXT("actors"), Items);
		return Respond(Json);
	}

	TUniquePtr<FHttpServerResponse> Actor(const FHttpServerRequest& Request)
	{
		AActor* Found = FindActor(EditorWorld(), Query(Request, TEXT("name")));
		if (!Found)
		{
			return Fail(EHttpServerResponseCodes::NotFound, TEXT("actor not found"));
		}
		FJson Json = ActorSummary(Found);
		Json->SetBoolField(TEXT("ok"), true);
		Json->SetStringField(TEXT("rotation"), Found->GetActorRotation().ToString());
		Json->SetObjectField(TEXT("scale"), VectorJson(Found->GetActorScale3D()));

		TArray<TSharedPtr<FJsonValue>> Components;
		for (const UActorComponent* Component : Found->GetComponents())
		{
			if (Component)
			{
				FJson C = MakeJson();
				C->SetStringField(TEXT("name"), Component->GetName());
				C->SetStringField(TEXT("class"), Component->GetClass()->GetName());
				Components.Add(MakeShared<FJsonValueObject>(C));
			}
		}
		Json->SetArrayField(TEXT("components"), Components);

		FJson Properties = MakeJson();
		int32 Count = 0;
		for (TFieldIterator<FProperty> It(Found->GetClass()); It && Count < 80; ++It)
		{
			const FProperty* Property = *It;
			if (!Property->HasAnyPropertyFlags(CPF_Edit) || Property->HasAnyPropertyFlags(CPF_Deprecated))
			{
				continue;
			}
			FString Value;
			Property->ExportText_InContainer(0, Value, Found, Found, Found, PPF_None);
			Properties->SetStringField(Property->GetName(), Value.Left(300));
			++Count;
		}
		Json->SetObjectField(TEXT("properties"), Properties);
		return Respond(Json);
	}

	TUniquePtr<FHttpServerResponse> Assets(const FHttpServerRequest& Request)
	{
		const FString Path = Query(Request, TEXT("path"), TEXT("/Game"));
		const FString ClassFilter = Query(Request, TEXT("class_name"));
		const int32 Limit = FMath::Clamp(FCString::Atoi(*Query(Request, TEXT("limit"), TEXT("100"))), 1, 1000);
		if (!Path.StartsWith(TEXT("/")))
		{
			return Fail(EHttpServerResponseCodes::BadRequest, TEXT("path must be a content path such as /Game/Maps"));
		}
		TArray<FAssetData> Found;
		FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get().GetAssetsByPath(FName(*Path), Found, true);
		TArray<TSharedPtr<FJsonValue>> Items;
		for (const FAssetData& Asset : Found)
		{
			if (Items.Num() >= Limit)
			{
				break;
			}
			const FString ClassName = Asset.AssetClassPath.GetAssetName().ToString();
			if (!ClassFilter.IsEmpty() && !ClassName.Contains(ClassFilter))
			{
				continue;
			}
			FJson Item = MakeJson();
			Item->SetStringField(TEXT("name"), Asset.AssetName.ToString());
			Item->SetStringField(TEXT("class"), ClassName);
			Item->SetStringField(TEXT("package"), Asset.PackageName.ToString());
			FString ParentClass;
			if (Asset.GetTagValue(FName(TEXT("ParentClass")), ParentClass))
			{
				Item->SetStringField(TEXT("parent_class"), ParentClass);
			}
			Items.Add(MakeShared<FJsonValueObject>(Item));
		}
		FJson Json = MakeJson();
		Json->SetBoolField(TEXT("ok"), true);
		Json->SetNumberField(TEXT("total"), Found.Num());
		Json->SetArrayField(TEXT("assets"), Items);
		return Respond(Json);
	}

	TUniquePtr<FHttpServerResponse> Telemetry(const FHttpServerRequest&)
	{
		FJson Json = MakeJson();
		Json->SetBoolField(TEXT("ok"), true);
		UWorld* World = PlayWorld();
		Json->SetBoolField(TEXT("pie"), World != nullptr);
		if (!World)
		{
			return Respond(Json);
		}
		if (const UShunyaTelemetrySubsystem* Telemetry = World->GetSubsystem<UShunyaTelemetrySubsystem>())
		{
			const FShunyaTelemetrySnapshot Snapshot = Telemetry->GetSnapshot();
			Json->SetNumberField(TEXT("fps"), Snapshot.AverageFps);
			Json->SetNumberField(TEXT("frame_ms"), Snapshot.AverageFrameMs);
			Json->SetNumberField(TEXT("worst_frame_ms"), Snapshot.WorstFrameMs);
			Json->SetNumberField(TEXT("frames"), static_cast<double>(Snapshot.FramesObserved));
			Json->SetNumberField(TEXT("world_seconds"), Snapshot.WorldSeconds);
			Json->SetNumberField(TEXT("actor_count"), Snapshot.ActorCount);
		}
		if (const APlayerController* Controller = World->GetFirstPlayerController())
		{
			if (const APawn* Pawn = Controller->GetPawn())
			{
				Json->SetStringField(TEXT("player_pawn"), Pawn->GetClass()->GetName());
				Json->SetObjectField(TEXT("player_location"), VectorJson(Pawn->GetActorLocation()));
			}
		}
		return Respond(Json);
	}

	// ------------------------------------------------------------------ commands

	enum class EScope : uint8 { Editor, Runtime, Either };

	FString ArgString(const TSharedPtr<FJsonObject>& Args, const TCHAR* Name)
	{
		FString Value;
		if (Args.IsValid())
		{
			Args->TryGetStringField(Name, Value);
		}
		return Value;
	}

	double ArgNumber(const TSharedPtr<FJsonObject>& Args, const TCHAR* Name)
	{
		double Value = 0.0;
		if (Args.IsValid())
		{
			Args->TryGetNumberField(Name, Value);
		}
		return Value;
	}

	TUniquePtr<FHttpServerResponse> Ok(const FString& Message, FJson Json = MakeJson())
	{
		Json->SetBoolField(TEXT("ok"), true);
		Json->SetStringField(TEXT("message"), Message);
		return Respond(Json);
	}

	TUniquePtr<FHttpServerResponse> SpawnActor(const TSharedPtr<FJsonObject>& Args)
	{
		UWorld* World = EditorWorld();
		if (!World || PlayWorld())
		{
			return Fail(EHttpServerResponseCodes::BadRequest, TEXT("no editor world, or PIE is running"));
		}
		const FString ClassPath = ArgString(Args, TEXT("class_path"));
		UClass* Class = LoadClass<AActor>(nullptr, *ClassPath);
		if (!Class || Class->HasAnyClassFlags(CLASS_Abstract))
		{
			return Fail(EHttpServerResponseCodes::BadRequest, FString::Printf(TEXT("'%s' is not a spawnable actor class"), *ClassPath));
		}
		const FScopedTransaction Transaction(NSLOCTEXT("ShunyaBridge", "SpawnActor", "Shunya Agent: Spawn Actor"));
		const FVector Location(ArgNumber(Args, TEXT("x")), ArgNumber(Args, TEXT("y")), ArgNumber(Args, TEXT("z")));
		AActor* Spawned = GEditor->AddActor(World->GetCurrentLevel(), Class, FTransform(Location), /*bSilent*/ true);
		if (!Spawned)
		{
			return Fail(EHttpServerResponseCodes::ServerError, TEXT("spawn failed"));
		}
		const FString Label = ArgString(Args, TEXT("label"));
		if (!Label.IsEmpty())
		{
			Spawned->SetActorLabel(Label);
		}
		return Ok(TEXT("spawned"), ActorSummary(Spawned));
	}

	TUniquePtr<FHttpServerResponse> SetProperty(const TSharedPtr<FJsonObject>& Args)
	{
		if (PlayWorld())
		{
			return Fail(EHttpServerResponseCodes::BadRequest, TEXT("stop PIE before editing the level"));
		}
		AActor* Target = FindActor(EditorWorld(), ArgString(Args, TEXT("actor")));
		if (!Target)
		{
			return Fail(EHttpServerResponseCodes::NotFound, TEXT("actor not found"));
		}
		FString PropertyPath = ArgString(Args, TEXT("property"));
		UObject* Object = Target;
		FString ComponentName, PropertyName;
		if (PropertyPath.Split(TEXT("."), &ComponentName, &PropertyName))
		{
			Object = nullptr;
			for (UActorComponent* Component : Target->GetComponents())
			{
				if (Component && Component->GetName().Equals(ComponentName, ESearchCase::IgnoreCase))
				{
					Object = Component;
					break;
				}
			}
			if (!Object)
			{
				return Fail(EHttpServerResponseCodes::NotFound, TEXT("component not found"));
			}
		}
		else
		{
			PropertyName = PropertyPath;
		}
		FProperty* Property = FindFProperty<FProperty>(Object->GetClass(), *PropertyName);
		if (!Property || !Property->HasAnyPropertyFlags(CPF_Edit) || Property->HasAnyPropertyFlags(CPF_EditConst))
		{
			return Fail(EHttpServerResponseCodes::BadRequest, TEXT("property not found or not editable"));
		}
		const FScopedTransaction Transaction(NSLOCTEXT("ShunyaBridge", "SetProperty", "Shunya Agent: Set Property"));
		Object->Modify();
		Object->PreEditChange(Property);
		const FString Value = ArgString(Args, TEXT("value"));
		if (Property->ImportText_InContainer(*Value, Object, Object, PPF_None) == nullptr)
		{
			return Fail(EHttpServerResponseCodes::BadRequest, TEXT("value could not be parsed for this property type"));
		}
		FPropertyChangedEvent Event(Property);
		Object->PostEditChangeProperty(Event);
		return Ok(TEXT("property set"));
	}

	TUniquePtr<FHttpServerResponse> Command(const FHttpServerRequest& Request)
	{
		const FUTF8ToTCHAR Converted(reinterpret_cast<const ANSICHAR*>(Request.Body.GetData()), Request.Body.Num());
		const FString BodyText(Converted.Length(), Converted.Get());
		TSharedPtr<FJsonObject> Body;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(BodyText), Body) || !Body.IsValid())
		{
			return Fail(EHttpServerResponseCodes::BadRequest, TEXT("body must be JSON {command, args}"));
		}
		const FString Name = Body->GetStringField(TEXT("command"));
		const TSharedPtr<FJsonObject>* ArgsPtr = nullptr;
		const TSharedPtr<FJsonObject> Args = Body->TryGetObjectField(TEXT("args"), ArgsPtr) && ArgsPtr ? *ArgsPtr : MakeShared<FJsonObject>();

		static const TMap<FString, EScope> Whitelist = {
			{TEXT("spawn_actor"), EScope::Editor},   {TEXT("set_property"), EScope::Editor}, {TEXT("load_level"), EScope::Editor},
			{TEXT("save_level"), EScope::Editor},    {TEXT("start_pie"), EScope::Editor},    {TEXT("stop_pie"), EScope::Editor},
			{TEXT("capture_screenshot"), EScope::Either}, {TEXT("console_stat"), EScope::Runtime},
		};
		const EScope* Required = Whitelist.Find(Name);
		if (!Required)
		{
			return Fail(EHttpServerResponseCodes::BadRequest, FString::Printf(TEXT("unknown command '%s'"), *Name));
		}
		const FString Scope = Header(Request, TEXT("X-Shunya-Scope"));
		const bool bScopeOk = (*Required == EScope::Either && (Scope == TEXT("editor") || Scope == TEXT("runtime")))
			|| (*Required == EScope::Editor && Scope == TEXT("editor"))
			|| (*Required == EScope::Runtime && Scope == TEXT("runtime"));
		if (!bScopeOk)
		{
			return Fail(EHttpServerResponseCodes::Forbidden, FString::Printf(TEXT("command '%s' is not allowed in scope '%s'"), *Name, *Scope));
		}
		UE_LOG(LogShunyaBridge, Log, TEXT("agent command: %s (scope %s)"), *Name, *Scope);

		if (Name == TEXT("spawn_actor"))
		{
			return SpawnActor(Args);
		}
		if (Name == TEXT("set_property"))
		{
			return SetProperty(Args);
		}
		if (Name == TEXT("load_level"))
		{
			const FString Path = ArgString(Args, TEXT("path"));
			if (!Path.StartsWith(TEXT("/")) || PlayWorld())
			{
				return Fail(EHttpServerResponseCodes::BadRequest, TEXT("path must be a package path like /Game/Maps/L_Test, and PIE must be stopped"));
			}
			return FEditorFileUtils::LoadMap(Path, false, false) ? Ok(TEXT("level loaded")) : Fail(EHttpServerResponseCodes::NotFound, TEXT("could not load level"));
		}
		if (Name == TEXT("save_level"))
		{
			UWorld* World = EditorWorld();
			if (!World || PlayWorld())
			{
				return Fail(EHttpServerResponseCodes::BadRequest, TEXT("no editor world, or PIE is running"));
			}
			return FEditorFileUtils::SaveLevel(World->GetCurrentLevel()) ? Ok(TEXT("level saved")) : Fail(EHttpServerResponseCodes::ServerError, TEXT("save failed (unsaved new level?)"));
		}
		if (Name == TEXT("start_pie"))
		{
			if (PlayWorld())
			{
				return Ok(TEXT("PIE already running"));
			}
			GEditor->RequestPlaySession(FRequestPlaySessionParams());
			return Ok(TEXT("PIE requested; poll /shunya/status until pie is true"));
		}
		if (Name == TEXT("stop_pie"))
		{
			if (PlayWorld())
			{
				GEditor->RequestEndPlayMap();
			}
			return Ok(TEXT("PIE stop requested"));
		}
		if (Name == TEXT("capture_screenshot"))
		{
			const FString File = FPaths::ConvertRelativePathToFull(
				FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Shunya") / FString::Printf(TEXT("agent_%s.png"), *FDateTime::Now().ToString()));
			FScreenshotRequest::RequestScreenshot(File, false, false);
			FJson Json = MakeJson();
			Json->SetStringField(TEXT("path"), File);
			return Ok(TEXT("screenshot requested; written on the next rendered frame"), Json);
		}
		if (Name == TEXT("console_stat"))
		{
			UWorld* World = PlayWorld();
			const FString Stat = ArgString(Args, TEXT("stat"));
			static const TSet<FString> AllowedStats = {TEXT("fps"), TEXT("unit"), TEXT("game"), TEXT("gpu")};
			if (!World || !AllowedStats.Contains(Stat))
			{
				return Fail(EHttpServerResponseCodes::BadRequest, TEXT("needs a running PIE session and stat in {fps, unit, game, gpu}"));
			}
			GEngine->Exec(World, *FString::Printf(TEXT("stat %s"), *Stat));
			return Ok(TEXT("stat toggled"));
		}
		return Fail(EHttpServerResponseCodes::BadRequest, TEXT("unhandled command"));
	}
} // namespace ShunyaBridge

class FShunyaAgentBridgeEditorModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		const UShunyaBridgeSettings* Settings = GetDefault<UShunyaBridgeSettings>();
		// Headless build/test runs (commandlets, -unattended automation) must not open the endpoint.
		if (!Settings->bEnabled || !GIsEditor || IsRunningCommandlet() || FApp::IsUnattended())
		{
			return;
		}
		Router = FHttpServerModule::Get().GetHttpRouter(Settings->Port);
		if (!Router.IsValid())
		{
			UE_LOG(LogShunyaBridge, Warning, TEXT("could not bind agent bridge on port %d"), Settings->Port);
			return;
		}
		using FHandler = TUniquePtr<FHttpServerResponse> (*)(const FHttpServerRequest&);
		auto Bind = [this](const TCHAR* Path, EHttpServerRequestVerbs Verb, FHandler Handler)
		{
			Routes.Add(Router->BindRoute(FHttpPath(Path), Verb, FHttpRequestHandler::CreateLambda(
				[Handler](const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
				{
					OnComplete(ShunyaBridge::Authorized(Request) ? Handler(Request) : ShunyaBridge::Fail(EHttpServerResponseCodes::Denied, TEXT("missing or wrong X-Shunya-Token")));
					return true;
				})));
		};
		Bind(TEXT("/shunya/status"), EHttpServerRequestVerbs::VERB_GET, &ShunyaBridge::Status);
		Bind(TEXT("/shunya/level"), EHttpServerRequestVerbs::VERB_GET, &ShunyaBridge::Level);
		Bind(TEXT("/shunya/actors"), EHttpServerRequestVerbs::VERB_GET, &ShunyaBridge::Actors);
		Bind(TEXT("/shunya/actor"), EHttpServerRequestVerbs::VERB_GET, &ShunyaBridge::Actor);
		Bind(TEXT("/shunya/assets"), EHttpServerRequestVerbs::VERB_GET, &ShunyaBridge::Assets);
		Bind(TEXT("/shunya/telemetry"), EHttpServerRequestVerbs::VERB_GET, &ShunyaBridge::Telemetry);
		Bind(TEXT("/shunya/command"), EHttpServerRequestVerbs::VERB_POST, &ShunyaBridge::Command);
		FHttpServerModule::Get().StartAllListeners();
		UE_LOG(LogShunyaBridge, Display, TEXT("Shunya Agent Bridge listening on http://127.0.0.1:%d/shunya"), Settings->Port);
	}

	virtual void ShutdownModule() override
	{
		if (Router.IsValid())
		{
			for (const FHttpRouteHandle& Route : Routes)
			{
				Router->UnbindRoute(Route);
			}
		}
		Routes.Empty();
		Router.Reset();
	}

private:
	TSharedPtr<IHttpRouter> Router;
	TArray<FHttpRouteHandle> Routes;
};

IMPLEMENT_MODULE(FShunyaAgentBridgeEditorModule, ShunyaAgentBridgeEditor);
