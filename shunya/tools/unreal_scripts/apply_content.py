# Runs INSIDE the Unreal Editor (UnrealEditor-Cmd -run=pythonscript), never in the studio process.
#
# The studio writes a request JSON and points SHUNYA_CONTENT_REQUEST at it. Modes:
#   apply    - create assets under /Game/AI_Staging from typed content jobs
#   validate - load assets and report facts about them
#   promote  - move everything from /Game/AI_Staging to /Game/Shunya (production content)
#
# This file is the whole surface content agents have on the editor: they describe jobs
# (texture, material, sound, level, level_additions, sequence); they never send Python.

import json
import os
import traceback

import unreal

EAL = unreal.EditorAssetLibrary
ASSET_TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()
STAGING = "/Game/AI_Staging"
PRODUCTION = "/Game/Shunya"
SHAPES = {"Cube", "Sphere", "Cylinder", "Cone", "Plane"}

REQUEST = json.load(open(os.environ["SHUNYA_CONTENT_REQUEST"], encoding="utf-8"))
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
CREATED = {}  # asset name -> package path, for references between jobs of one request


def log(msg):
    unreal.log("[shunya-content] " + str(msg))


def find_asset(name):
    """Resolve an asset by name: this request first, then staging, then production."""
    if name in CREATED:
        return CREATED[name]
    for root in (STAGING, PRODUCTION):
        for data in REGISTRY.get_assets_by_path(root, recursive=True) or []:
            if str(data.asset_name) == name:
                return str(data.package_name)
    return None


def require_asset(name):
    path = find_asset(name)
    if path is None:
        raise RuntimeError("asset '%s' does not exist in /Game/AI_Staging or /Game/Shunya" % name)
    asset = unreal.load_asset(path)
    if asset is None:
        raise RuntimeError("asset '%s' could not be loaded from %s" % (name, path))
    return asset


def fresh_asset(name, folder, asset_class, factory):
    path = "%s/%s/%s" % (STAGING, folder, name)
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    asset = ASSET_TOOLS.create_asset(name, "%s/%s" % (STAGING, folder), asset_class, factory)
    if asset is None:
        raise RuntimeError("could not create %s" % path)
    CREATED[name] = path
    return asset, path


def import_file(job, expected_class):
    source = os.path.join(PROJECT_DIR, job["source"])
    if not os.path.isfile(source):
        raise RuntimeError("source file missing: " + job["source"])
    folder = "%s/%s" % (STAGING, job["folder"])
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", source)
    task.set_editor_property("destination_path", folder)
    task.set_editor_property("destination_name", job["name"])
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    ASSET_TOOLS.import_asset_tasks([task])
    path = "%s/%s" % (folder, job["name"])
    asset = unreal.load_asset(path)
    if asset is None or not isinstance(asset, expected_class):
        raise RuntimeError("import of %s did not produce a %s" % (job["source"], expected_class.__name__))
    CREATED[job["name"]] = path
    return asset, path


# ----------------------------------------------------------------------------- job kinds


def job_texture(job):
    texture, path = import_file(job, unreal.Texture2D)
    texture.set_editor_property("srgb", bool(job.get("srgb", True)))
    EAL.save_loaded_asset(texture)
    return path, "%dx%d" % (texture.blueprint_get_size_x(), texture.blueprint_get_size_y())


def job_sound(job):
    sound, path = import_file(job, unreal.SoundWave)
    sound.set_editor_property("looping", bool(job.get("looping", False)))
    EAL.save_loaded_asset(sound)
    return path, "%.2fs" % sound.get_editor_property("duration")


def job_material(job):
    material, path = fresh_asset(job["name"], job["folder"], unreal.Material, unreal.MaterialFactoryNew())

    def node(cls, y, **props):
        n = MEL.create_material_expression(material, cls, -500, y)
        for key, value in props.items():
            n.set_editor_property(key, value)
        return n

    r, g, b = job["base_color"]
    color = node(unreal.MaterialExpressionConstant3Vector, 0, constant=unreal.LinearColor(r, g, b, 1.0))
    if job.get("texture"):
        tiling = float(job.get("uv_tiling", 1.0))
        coords = node(unreal.MaterialExpressionTextureCoordinate, 300, u_tiling=tiling, v_tiling=tiling)
        sample = node(unreal.MaterialExpressionTextureSample, 150, texture=require_asset(job["texture"]))
        MEL.connect_material_expressions(coords, "", sample, "UVs")
        multiply = node(unreal.MaterialExpressionMultiply, 80)
        MEL.connect_material_expressions(sample, "RGB", multiply, "A")
        MEL.connect_material_expressions(color, "", multiply, "B")
        MEL.connect_material_property(multiply, "", unreal.MaterialProperty.MP_BASE_COLOR)
    else:
        MEL.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)

    strength = float(job.get("emissive_strength", 0.0))
    if strength > 0.0:
        er, eg, eb = job.get("emissive_color") or job["base_color"]
        emissive = node(unreal.MaterialExpressionConstant3Vector, 450, constant=unreal.LinearColor(er * strength, eg * strength, eb * strength, 1.0))
        MEL.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    metallic = node(unreal.MaterialExpressionConstant, 600, r=float(job.get("metallic", 0.0)))
    MEL.connect_material_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)
    roughness = node(unreal.MaterialExpressionConstant, 700, r=float(job.get("roughness", 0.6)))
    MEL.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)

    MEL.recompile_material(material)
    EAL.save_loaded_asset(material)
    return path, "material with %d expressions" % MEL.get_num_material_expressions(material)


def vec(values, default=(0.0, 0.0, 0.0)):
    v = values or default
    return unreal.Vector(float(v[0]), float(v[1]), float(v[2]))


def rot(values):
    v = values or (0.0, 0.0, 0.0)  # pitch, yaw, roll
    return unreal.Rotator(pitch=float(v[0]), yaw=float(v[1]), roll=float(v[2]))


def spawn(actors, spec):
    kind = spec["type"]
    location, rotation = vec(spec.get("location")), rot(spec.get("rotation"))
    if kind == "static_mesh":
        if spec.get("shape") not in SHAPES:
            raise RuntimeError("shape must be one of %s" % sorted(SHAPES))
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, location, rotation)
        component = actor.static_mesh_component
        component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/" + spec["shape"]))
        if spec.get("material"):
            component.set_material(0, require_asset(spec["material"]))
    elif kind == "actor_class":
        cls = unreal.load_class(None, spec["class_path"])
        if cls is None:
            raise RuntimeError("class not found: %s (is the code that defines it merged and compiled?)" % spec["class_path"])
        actor = actors.spawn_actor_from_class(cls, location, rotation)
    elif kind == "player_start":
        actor = actors.spawn_actor_from_class(unreal.PlayerStart, location, rotation)
    elif kind == "directional_light":
        actor = actors.spawn_actor_from_class(unreal.DirectionalLight, location, rotation)
        light = actor.get_component_by_class(unreal.DirectionalLightComponent)
        light.set_intensity(float(spec.get("intensity", 6.0)))
        light.set_light_color(unreal.LinearColor(*(spec.get("color") or [1.0, 1.0, 1.0]), 1.0))
    elif kind == "point_light":
        actor = actors.spawn_actor_from_class(unreal.PointLight, location, rotation)
        light = actor.get_component_by_class(unreal.PointLightComponent)
        light.set_intensity(float(spec.get("intensity", 5000.0)))
        light.set_light_color(unreal.LinearColor(*(spec.get("color") or [1.0, 1.0, 1.0]), 1.0))
        light.set_attenuation_radius(float(spec.get("radius", 1500.0)))
    elif kind == "sky_light":
        actor = actors.spawn_actor_from_class(unreal.SkyLight, location, rotation)
        light = actor.get_component_by_class(unreal.SkyLightComponent)
        light.set_editor_property("real_time_capture", True)
        light.set_intensity(float(spec.get("intensity", 1.0)))
    elif kind == "sky_atmosphere":
        actor = actors.spawn_actor_from_class(unreal.SkyAtmosphere, location, rotation)
    elif kind == "exponential_height_fog":
        actor = actors.spawn_actor_from_class(unreal.ExponentialHeightFog, location, rotation)
    elif kind == "post_process":
        actor = actors.spawn_actor_from_class(unreal.PostProcessVolume, location, rotation)
        actor.set_editor_property("unbound", True)
        settings = actor.get_editor_property("settings")
        brightness = float(spec.get("exposure_brightness", 1.0))
        settings.set_editor_property("override_auto_exposure_min_brightness", True)
        settings.set_editor_property("override_auto_exposure_max_brightness", True)
        settings.set_editor_property("auto_exposure_min_brightness", brightness)
        settings.set_editor_property("auto_exposure_max_brightness", brightness)
        actor.set_editor_property("settings", settings)
    else:
        raise RuntimeError("unknown actor type '%s'" % kind)
    if actor is None:
        raise RuntimeError("could not spawn %s" % spec.get("label", kind))
    if kind in ("directional_light", "point_light", "sky_light"):
        # fully dynamic lighting: nothing to bake, so no "lighting needs to be rebuilt" in game
        actor.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    if spec.get("scale"):
        actor.set_actor_scale3d(vec(spec["scale"], (1.0, 1.0, 1.0)))
    if spec.get("label"):
        actor.set_actor_label(spec["label"])
    return actor


def editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def job_level(job):
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    path = "%s/%s/%s" % (STAGING, job["folder"], job["name"])
    if EAL.does_asset_exist(path):
        levels.load_level(path)
        for actor in actors.get_all_level_actors():
            if not isinstance(actor, (unreal.WorldSettings, unreal.Brush)):
                actors.destroy_actor(actor)
    elif not levels.new_level(path):
        raise RuntimeError("could not create level " + path)
    if job.get("game_mode"):
        game_mode = unreal.load_class(None, job["game_mode"])
        if game_mode is None:
            raise RuntimeError("game mode class not found: " + job["game_mode"])
        editor_world().get_world_settings().set_editor_property("default_game_mode", game_mode)
    for spec in job["actors"]:
        spawn(actors, spec)
    if not levels.save_current_level():
        raise RuntimeError("could not save level " + path)
    CREATED[job["name"]] = path
    return path, "%d actors placed" % len(job["actors"])


def job_level_additions(job):
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    path = find_asset(job["level"])
    if path is None:
        raise RuntimeError("level '%s' does not exist" % job["level"])
    if not levels.load_level(path):
        raise RuntimeError("could not load level " + path)
    labels = {spec.get("label") for spec in job["actors"] if spec.get("label")}
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label() in labels:  # re-running the job replaces, never duplicates
            actors.destroy_actor(actor)
    for spec in job["actors"]:
        spawn(actors, spec)
    if not levels.save_current_level():
        raise RuntimeError("could not save level " + path)
    CREATED.setdefault(job["level"], path)
    return path, "%d actors added" % len(job["actors"])


def job_sequence(job):
    fps = int(job.get("fps", 30))
    end = int(float(job["duration_seconds"]) * fps)
    sequence, path = fresh_asset(job["name"], job["folder"], unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    sequence.set_display_rate(unreal.FrameRate(fps, 1))
    sequence.set_playback_start(0)
    sequence.set_playback_end(end)

    camera = sequence.add_spawnable_from_class(unreal.CineCameraActor)
    camera.set_display_name("IntroCamera")
    track = camera.add_track(unreal.MovieScene3DTransformTrack)
    section = track.add_section()
    section.set_range(0, end)
    channels = section.get_all_channels()  # location xyz, rotation roll/pitch/yaw, scale xyz
    for key in job["camera_keys"]:
        frame = unreal.FrameNumber(int(float(key["time"]) * fps))
        x, y, z = key["location"]
        pitch, yaw, roll = key["rotation"]
        for index, value in ((0, x), (1, y), (2, z), (3, roll), (4, pitch), (5, yaw)):
            channels[index].add_key(frame, float(value))

    cuts = sequence.add_track(unreal.MovieSceneCameraCutTrack)
    cut = cuts.add_section()
    cut.set_range(0, end)
    cut.set_camera_binding_id(sequence.get_binding_id(camera))
    EAL.save_loaded_asset(sequence)
    return path, "%d camera keys over %d frames" % (len(job["camera_keys"]), end)


JOBS = {
    "texture": job_texture,
    "sound": job_sound,
    "material": job_material,
    "level": job_level,
    "level_additions": job_level_additions,
    "sequence": job_sequence,
}


def mode_apply():
    results = []
    for job in REQUEST["jobs"]:
        entry = {"kind": job.get("kind"), "name": job.get("name") or job.get("level")}
        try:
            path, detail = JOBS[job["kind"]](job)
            entry.update(ok=True, path=path, detail=detail)
        except Exception as e:  # report every job; one bad job must not hide the others
            entry.update(ok=False, error="%s: %s" % (type(e).__name__, e), trace=traceback.format_exc()[-1500:])
        log(entry)
        results.append(entry)
    return results


# ----------------------------------------------------------------------------- validate


def disk_bytes(package_path):
    rel = package_path.replace("/Game/", "", 1)
    for ext in (".uasset", ".umap"):
        candidate = os.path.join(PROJECT_DIR, "Content", rel + ext)
        if os.path.isfile(candidate):
            return os.path.getsize(candidate)
    return 0


def describe(path):
    facts = {"path": path, "ok": False}
    if not EAL.does_asset_exist(path):
        facts["error"] = "asset does not exist"
        return facts
    asset = unreal.load_asset(path)
    if asset is None:
        facts["error"] = "asset exists but failed to load"
        return facts
    facts.update(ok=True, asset_class=asset.get_class().get_name(), bytes=disk_bytes(path))
    if isinstance(asset, unreal.Texture2D):
        facts["size"] = [asset.blueprint_get_size_x(), asset.blueprint_get_size_y()]
    elif isinstance(asset, unreal.SoundWave):
        facts["duration"] = round(asset.get_editor_property("duration"), 3)
        facts["looping"] = bool(asset.get_editor_property("looping"))
        facts["ok"] = facts["duration"] > 0.0
    elif isinstance(asset, unreal.Material):
        facts["expressions"] = MEL.get_num_material_expressions(asset)
    elif isinstance(asset, unreal.LevelSequence):
        facts["frames"] = asset.get_playback_end() - asset.get_playback_start()
        facts["tracks"] = len(asset.get_tracks())
        facts["ok"] = facts["frames"] > 0 and facts["tracks"] > 0
    elif isinstance(asset, unreal.World):
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if not levels.load_level(path):
            facts.update(ok=False, error="level failed to open")
            return facts
        counts, labels, missing_materials = {}, [], []
        for actor in actors.get_all_level_actors():
            name = actor.get_class().get_name()
            counts[name] = counts.get(name, 0) + 1
            labels.append(actor.get_actor_label())
            if isinstance(actor, unreal.StaticMeshActor) and actor.static_mesh_component.get_material(0) is None:
                missing_materials.append(actor.get_actor_label())
        game_mode = editor_world().get_world_settings().get_editor_property("default_game_mode")
        facts.update(actors=counts, labels=sorted(labels), game_mode=game_mode.get_name() if game_mode else None, missing_materials=missing_materials)
        facts["ok"] = not missing_materials
    return facts


def mode_validate():
    paths = list(REQUEST.get("assets") or [])
    for name in REQUEST.get("names") or []:  # existing assets a task edited in place (e.g. a lighting pass on a level)
        paths.append(find_asset(name) or "%s/Missing/%s" % (STAGING, name))
    for root in REQUEST.get("roots") or []:
        for data in REGISTRY.get_assets_by_path(root, recursive=True) or []:
            if str(data.asset_class_path.asset_name) != "ObjectRedirector":
                paths.append(str(data.package_name))
    return [describe(p) for p in sorted(set(paths))]


# ----------------------------------------------------------------------------- promote


def mode_promote():
    results = []
    staged = [d for d in (REGISTRY.get_assets_by_path(STAGING, recursive=True) or []) if str(d.asset_class_path.asset_name) != "ObjectRedirector"]
    if any(str(d.asset_class_path.asset_name) == "World" for d in staged):
        unreal.EditorLoadingAndSavingUtils.new_blank_map(False)  # a level cannot be moved while it is open
    for data in staged:
        old = str(data.package_name)
        new = PRODUCTION + old[len(STAGING):]
        entry = {"from": old, "path": new}
        try:
            if EAL.does_asset_exist(new):
                EAL.delete_asset(new)
            if not EAL.rename_asset(old, new):
                raise RuntimeError("rename failed")
            entry["ok"] = True
        except Exception as e:
            entry.update(ok=False, error="%s: %s" % (type(e).__name__, e))
        results.append(entry)
    EAL.save_directory(PRODUCTION, only_if_is_dirty=False, recursive=True)
    if EAL.does_directory_exist(STAGING):
        EAL.delete_directory(STAGING)
    return results


def main():
    out = {"mode": REQUEST["mode"], "ok": False, "results": []}
    try:
        out["results"] = {"apply": mode_apply, "validate": mode_validate, "promote": mode_promote}[REQUEST["mode"]]()
        out["ok"] = all(r.get("ok") for r in out["results"])
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, e)
        out["trace"] = traceback.format_exc()[-3000:]
    with open(REQUEST["result"], "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    log("done: ok=%s, %d result(s)" % (out["ok"], len(out["results"])))


main()
