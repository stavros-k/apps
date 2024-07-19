import re

from . import utils
from .storage_models import (
    ui_cifs_config,
    ui_nfs_config,
    ui_acl_entries,
    ui_ix_volume_config,
    ui_host_path_config,
)

BIND_TYPES = ["host_path", "ix_volume"]
VOL_TYPES = ["volume", "nfs", "cifs"]
ALL_TYPES = BIND_TYPES + VOL_TYPES + ["tmpfs", "anonymous"]
PROPAGATION_TYPES = ["shared", "slave", "private", "rshared", "rslave", "rprivate"]


# Returns a volume mount object (Used in container's "volumes" level)
def vol_mount(data, ix_volumes=None):
    ix_volumes = ix_volumes or []
    vol_type = _get_docker_vol_type(data)

    volume = {
        "type": vol_type,
        "target": utils.valid_path(data.get("mount_path", "")),
        "read_only": data.get("read_only", False),
    }
    if vol_type == "bind":  # Default create_host_path is true in short-syntax
        volume.update(_get_bind_vol_config(data, ix_volumes))
    elif vol_type == "volume":
        volume.update(_get_volume_vol_config(data))
    elif vol_type == "tmpfs":
        volume.update(_get_tmpfs_vol_config(data))
    elif vol_type == "anonymous":
        volume["type"] = "volume"
        volume.update(_get_anonymous_vol_config(data))

    return volume


def storage_item(data, ix_volumes=None, perm_opts=None):
    ix_volumes = ix_volumes or []
    perm_opts = perm_opts or {}
    return {
        "vol_mount": vol_mount(data, ix_volumes),
        "vol": vol(data),
        "perms_item": perms_item(data, ix_volumes, perm_opts) if perm_opts else {},
    }


def perms_item(data, ix_volumes, opts=None):
    opts = opts or {}
    if not data.get("auto_permissions"):
        return {}

    if data.get("type") == "host_path":
        if data.get("host_path_config", {}).get("acl_enable", False):
            return {}
    if data.get("type") == "ix_volume":
        if data.get("ix_volume_config", {}).get("acl_enable", False):
            return {}

    if not ix_volumes:
        ix_volumes = []

    req_keys = ["mount_path", "mode", "uid", "gid"]
    for key in req_keys:
        if not opts.get(key):
            utils.throw_error(
                f"Expected opts passed to [perms_item] to have [{key}] key"
            )

    data.update({"mount_path": opts["mount_path"]})
    volume_mount = vol_mount(data, ix_volumes)

    return {
        "vol_mount": volume_mount,
        "perm_dir": {
            "dir": volume_mount["target"],
            "mode": opts["mode"],
            "uid": opts["uid"],
            "gid": opts["gid"],
            "chmod": opts.get("chmod", ""),
        },
    }


def _get_bind_vol_config(data, ix_volumes=None):
    ix_volumes = ix_volumes or []
    path = host_path(data, ix_volumes)
    if data.get("propagation", "rprivate") not in PROPAGATION_TYPES:
        utils.throw_error(
            f"Expected [propagation] to be one of [{', '.join(PROPAGATION_TYPES)}], got [{data['propagation']}]"
        )

    # https://docs.docker.com/storage/bind-mounts/#configure-bind-propagation
    return {
        "source": path,
        "bind": {
            "create_host_path": data.get("host_path_config", {}).get(
                "create_host_path", True
            ),
            "propagation": _get_valid_propagation(data),
        },
    }


def _get_volume_vol_config(data):
    if not data.get("volume_name"):
        utils.throw_error("Expected [volume_name] to be set for [volume] type")

    return {"source": data["volume_name"], "volume": _process_volume_config(data)}


def _get_anonymous_vol_config(data):
    return {"volume": _process_volume_config(data)}


mode_regex = re.compile(r"^0[0-7]{3}$")


def _get_tmpfs_vol_config(data):
    tmpfs = {}
    config = data.get("tmpfs_config", {})

    if config.get("size"):
        if not isinstance(config["size"], int):
            utils.throw_error("Expected [size] to be an integer for [tmpfs] type")
        if not config["size"] > 0:
            utils.throw_error("Expected [size] to be greater than 0 for [tmpfs] type")
        # Convert Mebibytes to Bytes
        tmpfs.update({"size": config["size"] * 1024 * 1024})

    if config.get("mode"):
        if not mode_regex.match(str(config["mode"])):
            utils.throw_error(
                f"Expected [mode] to be a octal string for [tmpfs] type, got [{config['mode']}]"
            )
        tmpfs.update({"mode": int(config["mode"], 8)})

    return {"tmpfs": tmpfs}


# Returns a volume object (Used in top "volumes" level)
def vol(data):
    if not data or _get_docker_vol_type(data) != "volume":
        return {}

    if not data.get("volume_name"):
        utils.throw_error("Expected [volume_name] to be set for [volume] type")

    if data["type"] == "nfs":
        return {data["volume_name"]: _get_top_level_nfs_volume(data.get("nfs_config"))}
    elif data["type"] == "cifs":
        return {
            data["volume_name"]: _get_top_level_cifs_volume(data.get("cifs_config"))
        }
    else:
        return {data["volume_name"]: {}}


def _is_host_path(data):
    return data.get("type") == "host_path"


def _get_valid_propagation(data):
    if not data.get("propagation"):
        return "rprivate"
    if not data["propagation"] in PROPAGATION_TYPES:
        utils.throw_error(
            f"Expected [propagation] to be one of [{', '.join(PROPAGATION_TYPES)}], got [{data['propagation']}]"
        )
    return data["propagation"]


def _is_ix_volume(data):
    return data.get("type") == "ix_volume"


# Returns the host path for a for either a host_path or ix_volume
def host_path(data, ix_volumes=None):
    ix_volumes = ix_volumes or []
    path = ""
    if _is_host_path(data):
        path = _get_host_path_from_host_path_config(data.get("host_path_config"))
    elif _is_ix_volume(data):
        path = _get_host_path_from_ix_volume_config(
            data.get("ix_volume_config"), ix_volumes
        )
    else:
        utils.throw_error(
            f"Expected [host_path()] to be called only for types [host_path, ix_volume], got [{data['type']}]"
        )

    return utils.valid_path(path)


# Returns the type of storage as used in docker-compose
def _get_docker_vol_type(data):
    if not data.get("type"):
        utils.throw_error("Expected [type] to be set for storage")

    if data["type"] not in ALL_TYPES:
        utils.throw_error(
            f"Expected storage [type] to be one of {ALL_TYPES}, got [{data['type']}]"
        )

    if data["type"] in BIND_TYPES:
        return "bind"
    elif data["type"] in VOL_TYPES:
        return "volume"
    else:
        return data["type"]


def _process_volume_config(data):
    return {"nocopy": data.get("volume_config", {}).get("nocopy", False)}


# Checkpoint


def _get_host_path_from_host_path_config(host_path_config) -> str:
    """
    Constructs a top level volume object for a host_path type
    """
    config = ui_host_path_config.parse_obj(host_path_config)
    if config.acl_enable:
        assert isinstance(config.acl, ui_acl_entries)
        return config.acl.path

    assert isinstance(config.path, str)
    return config.path


def _get_host_path_from_ix_volume_config(ix_volume_config, ix_volumes) -> str:
    """
    Constructs a top level volume object for a ix_volume type
    """
    config = ui_ix_volume_config.parse_obj(ix_volume_config)

    if not ix_volumes:
        utils.throw_error("Expected [ix_volumes] to be set for [ix_volume] type")

    path = ix_volumes.get(config.dataset_name, None)
    if not path:
        utils.throw_error(
            f"Expected the key [{config.dataset_name}] to be set in [ix_volumes]"
        )

    return path


def _get_top_level_cifs_volume(cifs_config):
    """
    Constructs a top level volume object for a cifs type
    """
    config = ui_cifs_config.parse_obj(cifs_config)

    opts = [
        f"user={config.username}",
        f"password={config.password}",
    ]
    if config.domain:
        opts.append(f"domain={config.domain}")

    if config.options:
        disallowed_opts = ["user", "password", "domain"]
        for opt in config.options:
            key = opt.split("=")[0]
            for disallowed in disallowed_opts:
                if key == disallowed:
                    utils.throw_error(
                        f"Expected [cifs_config.options] to not start with [{disallowed}] for [cifs] type"
                    )

            opts.append(opt)

    return {
        "driver_opts": {
            "type": "cifs",
            "device": f"//{config.server.lstrip('/')}/{config.path}",
            "o": f"{','.join(opts)}",
        },
    }


def _get_top_level_nfs_volume(nfs_config):
    """
    Constructs a top level volume object for a nfs type
    """
    config = ui_nfs_config.parse_obj(nfs_config)

    opts = [f"addr={config.server}"]
    if config.options:
        disallowed_opts = ["addr"]
        for opt in config.options:
            key = opt.split("=")[0]
            for disallowed in disallowed_opts:
                if key == disallowed:
                    utils.throw_error(
                        f"Expected [nfs_config.options] to not start with [{disallowed}] for [nfs] type"
                    )

            opts.append(opt)

    return {
        "driver_opts": {
            "type": "nfs",
            "device": f":{config.path}",
            "o": f"{','.join(opts)}",
        },
    }
