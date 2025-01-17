import numpy as np

import bpy
from bpy.props import *
from bpy.types import Operator

from ..utils import get_ml_active_object, is_modifier_local


class OBJECT_OT_ml_modifier_move_up(Operator):
    bl_idname = "object.ml_modifier_move_up"
    bl_label = "Move Modifier"
    bl_description = ("Move modifier up/down in the stack.\n"
                      "\n"
                      "Hold Shift to move it to the top/bottom")
    bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

    @classmethod
    def poll(cls, ontext):
        ob = get_ml_active_object()
        active_mod_index = ob.ml_modifier_active_index
        mods = ob.modifiers

        if not ob.modifiers:
            return False

        if active_mod_index == 0:
            return False

        mod = mods[active_mod_index]

        return is_modifier_local(ob, mod)

    def execute(self, context):
        ml_active_ob = get_ml_active_object()

        # Make using operators possible when an object is pinned
        override = context.copy()
        override['object'] = ml_active_ob

        active_mod_index = ml_active_ob.ml_modifier_active_index
        active_mod_name = ml_active_ob.modifiers[active_mod_index].name

        if self.shift:
            if float(bpy.app.version_string[0:4].strip(".")) >= 2.90:
                bpy.ops.object.modifier_move_to_index(modifier=active_mod_name, index=0)
            else:
                for _ in range(active_mod_index):
                    bpy.ops.object.modifier_move_up(override, modifier=active_mod_name)
            ml_active_ob.ml_modifier_active_index = 0
        else:
            bpy.ops.object.modifier_move_up(override, modifier=active_mod_name)
            ml_active_ob.ml_modifier_active_index = np.clip(active_mod_index - 1, 0, 999)

        return {'FINISHED'}

    def invoke(self, context, event):
        self.shift = event.shift

        return self.execute(context)
