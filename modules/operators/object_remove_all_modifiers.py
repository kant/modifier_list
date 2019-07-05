import bpy
from bpy.props import *
from bpy.types import Operator

from ..utils import get_ml_active_object


class OBJECT_OT_ml_remove_all_modifiers(Operator):
    bl_idname = "object.ml_remove_all_modifiers"
    bl_label = "Remove All Modifiers"
    bl_description = "Remove all modifiers from the selected object(s)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obs = context.selected_objects

        if not obs:
            self.report({'INFO'}, "No selection")
            return {'CANCELLED'}

        obs_have_mods = False

        for ob in obs:
            for mod in ob.modifiers:
                ob.modifiers.remove(mod)
                obs_have_mods = True

        if not obs_have_mods:
            self.report({'INFO'}, "No modifiers to remove")
            return {'CANCELLED'}

        self.report({'INFO'}, "Removed all modifiers")

        return {'FINISHED'}