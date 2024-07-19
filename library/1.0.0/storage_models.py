from pydantic import BaseModel, model_validator
from typing import Optional
from enum import Enum
from . import utils


class ui_storage_type(str, Enum):
    anonymous = "anonymous"
    host_path = "host_path"
    ix_volume = "ix_volume"
    tmpfs = "tmpfs"
    cifs = "cifs"
    nfs = "nfs"


class ui_tmpfs_config(BaseModel, extra="allow"):
    size: int
    mode: str


class ui_acl_options(BaseModel, extra="allow"):
    force: bool = False


class ui_acl_entry(BaseModel, extra="allow"):
    access: str
    id: str
    id_type: str


class ui_acl_entries(BaseModel, extra="allow"):
    path: str
    entries: Optional[list[ui_acl_entry]] = None
    options: Optional[ui_acl_options] = None


class ui_host_path_config(BaseModel, extra="allow"):
    path: Optional[str] = None
    acl_enable: bool = False
    acl: Optional[ui_acl_entries] = None

    @model_validator(mode="after")
    def validate_host_path_config(self):
        if self.acl_enable:
            if not self.acl:
                utils.throw_error("Expected [acl] to be set when [acl_enable] is true")
        elif not self.path:
            utils.throw_error("Expected [path] to be set when [acl_enable] is false")
        return self


class ui_cifs_config(BaseModel, extra="allow"):
    server: str
    path: str
    username: str
    password: str
    domain: Optional[str] = None
    options: Optional[list[str]] = None


class ui_nfs_config(BaseModel, extra="allow"):
    server: str
    path: str
    options: Optional[list[str]] = None


class ui_ix_volume_config(BaseModel, extra="allow"):
    dataset_name: str
    acl_enable: bool = False
    acl_entries: Optional[ui_acl_entries] = None

    @model_validator(mode="after")
    def validate_ix_volume_config(self):
        if self.acl_enable:
            if not self.acl_entries:
                utils.throw_error(
                    "Expected [acl_entries] to be set when [acl_enable] is true"
                )
        return self


class ui_storage_item(BaseModel, extra="allow"):
    type: ui_storage_type
    read_only: bool = False
    mount_path: str

    volume_name: Optional[str] = None

    tmpfs_config: Optional[ui_tmpfs_config] = None
    host_path_config: Optional[ui_host_path_config] = None
    ix_volume_config: Optional[ui_ix_volume_config] = None
    cifs_config: Optional[ui_cifs_config] = None
    nfs_config: Optional[ui_nfs_config] = None

    @model_validator(mode="after")
    def validate_storage_item(self):
        if self.type == ui_storage_type.tmpfs:
            if not self.tmpfs_config:
                utils.throw_error("Expected [tmpfs_config] to be set for tmpfs type")
        elif self.type == ui_storage_type.host_path:
            if not self.host_path_config:
                utils.throw_error(
                    "Expected [host_path_config] to be set for host_path type"
                )
        elif self.type == ui_storage_type.ix_volume:
            if not self.ix_volume_config:
                utils.throw_error(
                    "Expected [ix_volume_config] to be set for ix_volume type"
                )
        elif self.type == ui_storage_type.cifs:
            if not self.cifs_config:
                utils.throw_error("Expected [cifs_config] to be set for cifs type")
        elif self.type == ui_storage_type.nfs:
            if not self.nfs_config:
                utils.throw_error("Expected [nfs_config] to be set for nfs type")
        elif self.type == ui_storage_type.anonymous:
            if self.volume_name:
                utils.throw_error(
                    "Expected [volume_name] to be empty for anonymous type"
                )
        return self


# Mapping for ui types to docker types
UI_TO_DOCKER_TYPES = {
    ui_storage_type.anonymous: "volume",
    ui_storage_type.host_path: "bind",
    ui_storage_type.ix_volume: "bind",
    ui_storage_type.tmpfs: "tmpfs",
    ui_storage_type.cifs: "volume",
    ui_storage_type.nfs: "volume",
}
