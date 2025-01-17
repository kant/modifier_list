import math
import numpy as np

import bpy
from bpy.app.handlers import persistent
from bpy.props import *
from bpy.types import (
    Menu,
    Operator,
    Panel,
    PropertyGroup,
    UIList
)

# Check if the modifier layouts can be imported from Blender. If not,
# import the layouts included in this addon. This is needed for 2.90 and
# later because the modifier layouts have been moved from Python into C
# in Blender 2.90 since 5.6.2020.
from bl_ui import properties_data_modifier
if hasattr(properties_data_modifier.DATA_PT_modifiers, "ARRAY"):
    from bl_ui.properties_data_modifier import DATA_PT_modifiers
else:
    from .properties_data_modifier import DATA_PT_modifiers

from . import ml_modifier_layouts
from .. import icons, modifier_categories
from ..utils import (
    favourite_modifiers_names_icons_types,
    get_gizmo_object_from_modifier,
    get_ml_active_object,
    is_modifier_disabled,
    is_modifier_local
)


BLENDER_VERSION_MAJOR_POINT_MINOR = float(bpy.app.version_string[0:4].strip("."))


# UI elements
# =======================================================================

def show_in_editmode_button(modifier, layout, pcoll, use_in_list):
    row = layout.row(align=True)

    if modifier.type in modifier_categories.DONT_SUPPORT_SHOW_IN_EDITMODE:
        empy_icon = pcoll['EMPTY_SPACE']
        row.label(text="", translate=False, icon_value=empy_icon.icon_id)
        return

    if not use_in_list:
        row.active = modifier.show_viewport

    if not modifier.show_viewport and use_in_list:
        show_in_editmode_on = pcoll['SHOW_IN_EDITMODE_ON_INACTIVE']
        show_in_editmode_off = pcoll['SHOW_IN_EDITMODE_OFF_INACTIVE']
    else:
        show_in_editmode_on = pcoll['SHOW_IN_EDITMODE_ON']
        show_in_editmode_off = pcoll['SHOW_IN_EDITMODE_OFF']

    show = modifier.show_in_editmode
    icon = show_in_editmode_on.icon_id if show else show_in_editmode_off.icon_id
    row.prop(modifier, "show_in_editmode", text="", icon_value=icon, emboss=not use_in_list)


def use_apply_on_spline_button(modifier, layout, pcoll, use_in_list):
    row = layout.row(align=True)

    if modifier.type not in modifier_categories.SUPPORT_USE_APPLY_ON_SPLINE:
        empy_icon = pcoll['EMPTY_SPACE']
        row.label(text="", translate=False, icon_value=empy_icon.icon_id)
        return

    use_apply_on_spline_on = pcoll['USE_APPLY_ON_SPLINE_ON']
    use_apply_on_spline_off = pcoll['USE_APPLY_ON_SPLINE_OFF']
    apply_on = modifier.use_apply_on_spline
    icon = use_apply_on_spline_on.icon_id if apply_on else use_apply_on_spline_off.icon_id
    row.prop(modifier, "use_apply_on_spline", text="", icon_value=icon, emboss=not use_in_list)


def show_on_cage_button(object, modifier, layout, pcoll, use_in_list):
    support_show_on_cage = modifier_categories.SUPPORT_SHOW_ON_CAGE

    if modifier.type not in support_show_on_cage:
        return False

    mods = object.modifiers
    mod_index = mods.find(modifier.name)

    # Check if some modifier before this has show_in_editmode on
    # and doesn't have show_on_cage setting.
    is_before_show_in_editmode_on = False
    end_index = np.clip(mod_index, 1, 99)

    for mod in mods[0:end_index]:
        if mod.show_in_editmode and mod.type not in support_show_on_cage:
            is_before_show_in_editmode_on = True
            break

    if is_before_show_in_editmode_on:
        return False

    # Check if some modifier after this has show_in_editmode and
    # show_on_cage both on and also is visible in the viewport.
    is_after_show_on_cage_on = False

    for mod in mods[(mod_index + 1):(len(mods))]:
        if (mod.show_viewport and mod.show_in_editmode and mod.show_on_cage):
            is_after_show_on_cage_on = True
            break

    # Button
    row = layout.row(align=True)
    show_on_cage_on = pcoll['SHOW_ON_CAGE_ON']
    show_on_cage_off = pcoll['SHOW_ON_CAGE_OFF']

    if (not modifier.show_viewport or not modifier.show_in_editmode
            or is_after_show_on_cage_on):
        if use_in_list:
            show_on_cage_on = pcoll['SHOW_ON_CAGE_ON_INACTIVE']
            show_on_cage_off = pcoll['SHOW_ON_CAGE_OFF_INACTIVE']
        else:
            row.active = False

    icon = show_on_cage_on.icon_id if modifier.show_on_cage else show_on_cage_off.icon_id
    row.prop(modifier, "show_on_cage", text="", icon_value=icon, emboss=not use_in_list)

    return True


def curve_properties_context_change_button(layout, pcoll, use_in_list):
    sub = layout.row(align=True)
    empy_icon = pcoll['EMPTY_SPACE']

    if use_in_list:
        sub.label(text="", translate=False, icon_value=empy_icon.icon_id)
    else:
        sub.operator("wm.properties_context_change", icon='PROPERTIES',
                     emboss=False).context = "PHYSICS"


def mesh_properties_context_change_button(modifier, layout, use_in_list):
    if bpy.context.area.type != 'PROPERTIES' or use_in_list:
        return False

    if bpy.app.version[0] == 2 and bpy.app.version[1] < 82:
        have_phys_context_button = {
            'CLOTH',
            'COLLISION',
            'FLUID_SIMULATION',
            'DYNAMIC_PAINT',
            'SMOKE',
            'SOFT_BODY'
        }
    else:
        have_phys_context_button = {
            'CLOTH',
            'COLLISION',
            'FLUID',
            'DYNAMIC_PAINT',
            'SOFT_BODY'
        }

    if modifier.type in have_phys_context_button:
        row = layout.row(align=True)
        row.operator("wm.properties_context_change", icon='PROPERTIES',
                     emboss=False).context = "PHYSICS"
        return True

    if modifier.type == 'PARTICLE_SYSTEM':
        row = layout.row(align=True)
        row.operator("wm.properties_context_change", icon='PROPERTIES',
                     emboss=False).context = "PARTICLES"
        return True

    return False


def modifier_visibility_buttons(modifier, layout, use_in_list=False):
    """This handles the modifier visibility buttons (and also the
    properties_context_change button) to match the behaviour of the
    regular UI .

    When called, adds those buttons, for the given modifier, in their
    correct state, to the specified (sub-)layout.

    Note: some modifiers show show_on_cage in the regular UI only if,
    for example, an object to use for deforming is specified. Eg.
    Armatature modifier requires an armature object to be specified in
    order to show the button. This function doesn't take that into
    account but instead shows the button always in those cases. It's
    easier to achieve and hardly makes a difference.
    """
    pcoll = icons.preview_collections["main"]
    empy_icon = pcoll['EMPTY_SPACE']

    # Main layout
    row = layout.row(align=True)
    row.scale_x = 1.0 if use_in_list else 1.2

    # show_render and show_viewport
    sub = row.row(align=True)

    # Hide visibility toggles for collision modifier as they are not
    # used in the regular UI either (apparently can cause problems
    # in some scenes).
    if modifier.type == 'COLLISION':
        sub.label(text="", translate=False, icon_value=empy_icon.icon_id)
        sub.label(text="", translate=False, icon_value=empy_icon.icon_id)
    else:
        sub.prop(modifier, "show_render", text="", emboss=not use_in_list)
        sub.prop(modifier, "show_viewport", text="", emboss=not use_in_list)

    # show_in_editmode
    show_in_editmode_button(modifier, row, pcoll, use_in_list)

    ob = get_ml_active_object()

    # No use_apply_on_spline or show_on_cage for lattices
    if ob.type == 'LATTICE':
        return

    # use_apply_on_spline or properties_context_change
    if ob.type != 'MESH':
        if modifier.type == 'SOFT_BODY':
            curve_properties_context_change_button(row, pcoll, use_in_list)
        else:
            use_apply_on_spline_button(modifier, row, pcoll, use_in_list)
        return

    # show_on_cage or properties_context_change
    show_on_cage_added = show_on_cage_button(ob, modifier, row, pcoll, use_in_list)
    context_change_added = False
    if not show_on_cage_added:
        context_change_added = mesh_properties_context_change_button(modifier, row, use_in_list)

    # Make icons align nicely if neither show_on_cage nor
    # properties_context_change was added.
    if not show_on_cage_added and not context_change_added:
        sub = row.row(align=True)
        sub.label(text="", translate=False, icon_value=empy_icon.icon_id)


class MESH_MT_ml_add_modifier_menu(Menu):
    bl_label = "Add Modifier"
    bl_description = "Add a procedural operation/effect to the active object"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.alignment = 'LEFT'

        col = row.column()
        col.label(text="Modify")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.MESH_MODIFY_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        col.label(text="Generate")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.MESH_GENERATE_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        col.label(text="Deform")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.MESH_DEFORM_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        label = "Simulate" if BLENDER_VERSION_MAJOR_POINT_MINOR < 2.90 else "Physics"
        col.label(text=label)
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.MESH_SIMULATE_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod


class CURVE_MT_ml_add_modifier_menu(Menu):
    bl_label = "Add Modifier"
    bl_description = "Add a procedural operation/effect to the active object"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.alignment = 'LEFT'

        col = row.column()
        col.label(text="Modify")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.CURVE_MODIFY_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        col.label(text="Generate")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.CURVE_GENERATE_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        col.label(text="Deform")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.CURVE_DEFORM_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        label = "Simulate" if BLENDER_VERSION_MAJOR_POINT_MINOR < 2.90 else "Physics"
        col.label(text=label)
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.CURVE_SIMULATE_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod


class LATTICE_MT_ml_add_modifier_menu(Menu):
    bl_label = "Add Modifier"
    bl_description = "Add a procedural operation/effect to the active object"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.alignment = 'LEFT'

        col = row.column()
        col.label(text="Modify")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.LATTICE_MODIFY_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        col.label(text="Deform")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.LATTICE_DEFORM_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        label = "Simulate" if BLENDER_VERSION_MAJOR_POINT_MINOR < 2.90 else "Physics"
        col.label(text=label)
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.LATTICE_SIMULATE_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod


class POINTCLOUD_MT_ml_add_modifier_menu(Menu):
    bl_label = "Add Modifier"
    bl_description = "Add a procedural operation/effect to the active object"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.alignment = 'LEFT'

        col = row.column()
        col.label(text="Generate")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.POINTCLOUD_GENERATE_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod


class VOLUME_MT_ml_add_modifier_menu(Menu):
    bl_label = "Add Modifier"
    bl_description = "Add a procedural operation/effect to the active object"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.alignment = 'LEFT'

        col = row.column()
        col.label(text="Generate")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.VOLUME_GENERATE_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod

        col = row.column()
        col.label(text="Deform")
        col.separator(factor=0.3)
        for name, icon, mod in modifier_categories.VOLUME_DEFORM_NAMES_ICONS_TYPES:
            col.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod


class OBJECT_UL_ml_modifier_list(UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        mod = item

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if mod:
                row = layout.row()
                row.alert = is_modifier_disabled(mod)
                row.label(text="", translate=False, icon_value=layout.icon(mod))

                layout.prop(mod, "name", text="", emboss=False, icon_value=icon)

                modifier_visibility_buttons(mod, layout, use_in_list=True)
            else:
                layout.label(text="", translate=False, icon_value=icon)

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)


class OBJECT_PT_ml_modifier_extras(Panel):
    bl_label = "Modifier Extras"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'

    def draw(self, context):
        layout = self.layout
        layout.ui_units_x = 11

        if BLENDER_VERSION_MAJOR_POINT_MINOR >= 2.92:
            ob = get_ml_active_object()
            if ob.modifiers:
                active_mod = ob.modifiers[ob.ml_modifier_active_index]
                layout.operator("object.modifier_copy_to_selected").modifier = active_mod.name
            else:
                row = layout.row()
                row.enabled = False
                row.operator("object.modifier_copy_to_selected")
            layout.separator()

        layout.label(text="Syncronize Modifiers Between Instances:")
        layout.operator("object.ml_sync_active_modifier_between_instances", text="Active Only")
        layout.operator("object.ml_sync_all_modifiers_between_instances", text="All")

        layout.separator()

        layout.operator("wm.ml_favourite_modifiers_configuration_popup")


class OBJECT_PT_ml_gizmo_object_settings(Panel):
    bl_label = "Gizmo Settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'

    def draw(self, context):
        layout = self.layout

        ob = get_ml_active_object()

        # Avoid an error when a lattice gizmo is seleted when using the
        # popup because in that case the popover doesn't get closed when
        # running an operator.
        if not ob.modifiers:
            return

        active_mod_index = ob.ml_modifier_active_index
        active_mod = ob.modifiers[active_mod_index]
        gizmo_ob = get_gizmo_object_from_modifier(active_mod)

        # Avoid an error when the gizmo is deleted when using the popup
        # because in that case the popover doesn't get closed when
        # running an operator.
        if not gizmo_ob:
            layout.label(text="Deleted gizmo")
            return

        layout.prop(gizmo_ob, "name", text="")

        if gizmo_ob.type == 'EMPTY':
            layout.prop(gizmo_ob, "empty_display_type", text="")
            layout.prop(gizmo_ob, "empty_display_size", text="Display Size")

        layout.separator()

        layout.operator("object.ml_gizmo_object_reset_transform", text="Reset Transform")

        layout.label(text="Location:")
        col = layout.column()
        col.prop(gizmo_ob, "location", text="")

        layout.label(text="Rotation:")
        col = layout.column()
        col.prop(gizmo_ob, "rotation_euler", text="")

        layout.label(text="Parent")

        is_ob_parented_to_gizmo = True if ob.parent == gizmo_ob else False
        is_gizmo_parented_to_ob = True if gizmo_ob.parent == ob else False

        col = layout.column(align=True)

        sub = col.row()
        if is_ob_parented_to_gizmo:
            sub.enabled = False
        depress = is_gizmo_parented_to_ob
        unset = is_gizmo_parented_to_ob
        sub.operator("object.ml_gizmo_object_parent_set", text="Gizmo To Active Object",
                        depress=depress).unset = unset

        sub = col.row()
        if is_gizmo_parented_to_ob:
            sub.enabled = False
        depress = is_ob_parented_to_gizmo
        unset = is_ob_parented_to_gizmo
        sub.operator("object.ml_gizmo_object_child_set", text="Active Object To Gizmo",
                        depress=depress).unset = unset

        layout.separator()

        layout.operator("object.ml_select", text="Select Gizmo").object_name = gizmo_ob.name

        if gizmo_ob.type in {'EMPTY', 'LATTICE'} and "_Gizmo" in gizmo_ob.name:
            layout.operator("object.ml_gizmo_object_delete")


# UI
# =======================================================================

def modifiers_ui(context, layout, num_of_rows=False, use_in_popup=False):
    ml_props = bpy.context.window_manager.modifier_list
    ob = get_ml_active_object()
    active_mod_index = ob.ml_modifier_active_index
    prefs = bpy.context.preferences.addons["modifier_list"].preferences
    pcoll = icons.preview_collections["main"]

    # Ensure the active index is never out of range. That can happen if
    # a modifier gets deleted without using Modifier List, e.g. when
    # removing a Cloth modifier from within the physics panel.
    if ob.modifiers and active_mod_index > len(ob.modifiers) - 1:
        layout.label(text="The active modifier index has gotten out of range...")
        layout.operator("object.ml_reset_modifier_active_index")
        return

    if ob.modifiers:
        # This makes operators work without passing the active modifier
        # to them manually as an argument.
        layout.context_pointer_set("modifier", ob.modifiers[ob.ml_modifier_active_index])

    # === Favourite modifiers ===
    col = layout.column(align=True)

    # Check if an item or the next item in
    # favourite_modifiers_names_icons_types has a value and add rows
    # and buttons accordingly (2 or 3 buttons per row).
    fav_names_icons_types_iter = favourite_modifiers_names_icons_types()

    place_three_per_row = prefs.favourites_per_row == '3'

    for name, icon, mod in fav_names_icons_types_iter:
        next_mod_1 = next(fav_names_icons_types_iter)
        if place_three_per_row:
            next_mod_2 = next(fav_names_icons_types_iter)

        if name or next_mod_1[0] or (place_three_per_row and next_mod_2[0]):
            row = col.row(align=True)

            if name:
                icon = icon if prefs.use_icons_in_favourites else 'NONE'
                row.operator("object.ml_modifier_add", text=name, icon=icon).modifier_type = mod
            else:
                row.label(text="")

            if next_mod_1[0]:
                icon = next_mod_1[1] if prefs.use_icons_in_favourites else 'NONE'
                row.operator("object.ml_modifier_add", text=next_mod_1[0],
                                icon=icon).modifier_type = next_mod_1[2]
            else:
                row.label(text="")

            if place_three_per_row:
                if next_mod_2[0]:
                    icon = next_mod_2[1] if prefs.use_icons_in_favourites else 'NONE'
                    row.operator("object.ml_modifier_add", text=next_mod_2[0],
                                icon=icon).modifier_type = next_mod_2[2]
                else:
                    row.label(text="")

    # === Modifier search and menu ===
    col = layout.column()
    row = col.split(factor=0.59)
    row.enabled = ob.library is None or ob.override_library is not None
    if ob.type == 'MESH':
        row.prop_search(ml_props, "modifier_to_add_from_search", ml_props, "mesh_modifiers",
                        text="", icon='MODIFIER')
        row.menu("MESH_MT_ml_add_modifier_menu")
    elif ob.type in {'CURVE', 'SURFACE', 'FONT'}:
        row.prop_search(ml_props, "modifier_to_add_from_search", ml_props, "curve_modifiers",
                        text="", icon='MODIFIER')
        row.menu("CURVE_MT_ml_add_modifier_menu")
    elif ob.type == 'LATTICE':
        row.prop_search(ml_props, "modifier_to_add_from_search", ml_props, "lattice_modifiers",
                        text="", icon='MODIFIER')
        row.menu("LATTICE_MT_ml_add_modifier_menu")
    elif ob.type == 'POINTCLOUD':
        row.prop_search(ml_props, "modifier_to_add_from_search", ml_props, "pointcloud_modifiers",
                        text="", icon='MODIFIER')
        row.menu("POINTCLOUD_MT_ml_add_modifier_menu")
    elif ob.type == 'VOLUME':
        row.prop_search(ml_props, "modifier_to_add_from_search", ml_props, "volume_modifiers",
                        text="", icon='MODIFIER')
        row.menu("VOLUME_MT_ml_add_modifier_menu")

    # === Modifier list ===
    # Get the list index from
    # ml_props.ml_active_object_modifier_active_index instead of
    # ob.ml_modifier_active_index because library overrides prevent
    # editing that value directly.
    # ml_props.ml_active_object_modifier_active_index has get and set
    # methods for accessing ob.ml_modifier_active_index indirectly.
    layout.template_list("OBJECT_UL_ml_modifier_list", "", ob, "modifiers",
                         ml_props, "active_object_modifier_active_index", rows=num_of_rows,
                         sort_reverse=prefs.reverse_list)

    # When sub.scale_x is 1.5 and the area/region is narrow, the buttons
    # don't align properly, so some manual work is needed.
    if use_in_popup:
        align_button_groups = prefs.popup_width <= 250
    elif context.area.type == 'VIEW_3D':
        align_button_groups = context.region.width <= 283
    else:
        align_button_groups = context.area.width <= 291

    row = layout.row(align=align_button_groups)

    # === Modifier batch operators ===
    sub = row.row(align=True)
    sub.scale_x = 3 if align_button_groups else 1.34

    icon = pcoll['TOGGLE_ALL_MODIFIERS_VISIBILITY']
    sub.operator("view3d.ml_toggle_all_modifiers", icon_value=icon.icon_id, text="")

    icon = pcoll['APPLY_ALL_MODIFIERS']
    sub.operator("view3d.ml_apply_all_modifiers", icon_value=icon.icon_id, text="")

    icon = pcoll['DELETE_ALL_MODIFIERS']
    sub.operator("view3d.ml_remove_all_modifiers", icon_value=icon.icon_id, text="")

    sub_sub = sub.row(align=True)
    sub_sub.scale_x = 0.65 if align_button_groups else 0.85
    sub_sub.popover("OBJECT_PT_ml_modifier_extras", icon='DOWNARROW_HLT', text="")

    # === List manipulation ===
    sub = row.row(align=True)
    sub.scale_x = 3 if align_button_groups else 1.5
    if not align_button_groups:
        sub.alignment = 'RIGHT'

    move_up_icon = 'TRIA_DOWN' if prefs.reverse_list else 'TRIA_UP'
    move_down_icon = 'TRIA_UP' if prefs.reverse_list else 'TRIA_DOWN'

    if not prefs.reverse_list:
        sub.operator("object.ml_modifier_move_up", icon=move_up_icon, text="")
        sub.operator("object.ml_modifier_move_down", icon=move_down_icon, text="")
    else:
        sub.operator("object.ml_modifier_move_down", icon=move_down_icon, text="")
        sub.operator("object.ml_modifier_move_up", icon=move_up_icon, text="")

    sub.operator("object.ml_modifier_remove", icon='REMOVE', text="")

    # === Modifier settings ===
    if not ob.modifiers:
        return

    active_mod = ob.modifiers[active_mod_index]
    all_mods = modifier_categories.ALL_MODIFIERS_NAMES_ICONS_TYPES
    active_mod_icon = next(icon for _, icon, mod in all_mods if mod == active_mod.type)
    is_active_mod_local = is_modifier_local(ob, active_mod)

    col = layout.column(align=True)

    # === General settings ===
    box = col.box()

    if not prefs.hide_general_settings_region:
        row = box.row()

        sub = row.row()
        sub.alert = is_modifier_disabled(active_mod)
        sub.label(text="", icon=active_mod_icon)
        sub.prop(active_mod, "name", text="")

        modifier_visibility_buttons(active_mod, row)

    row = box.row()

    sub = row.row(align=True)

    if active_mod.type == 'PARTICLE_SYSTEM':
        ps = active_mod.particle_system
        if ps.settings.render_type in {'COLLECTION', 'OBJECT'}:
            sub.operator("object.duplicates_make_real", text="Convert")
        elif ps.settings.render_type == 'PATH':
            sub.operator("object.modifier_convert", text="Convert").modifier = active_mod.name
    else:
        sub.scale_x = 5
        icon = pcoll['APPLY_MODIFIER']
        sub.operator("object.ml_modifier_apply", text="",
                    icon_value=icon.icon_id).modifier = active_mod.name

        if active_mod.type in modifier_categories.SUPPORT_APPLY_AS_SHAPE_KEY:
            icon = pcoll['APPLY_MODIFIER_AS_SHAPEKEY']
            sub.operator("object.ml_modifier_apply_as_shapekey", text="",
                        icon_value=icon.icon_id).modifier = active_mod.name
            if BLENDER_VERSION_MAJOR_POINT_MINOR >= 2.90:
                icon = pcoll['SAVE_MODIFIER_AS_SHAPEKEY']
                sub.operator("object.ml_modifier_save_as_shapekey", text="",
                             icon_value=icon.icon_id).modifier = active_mod.name

        if active_mod.type not in modifier_categories.DONT_SUPPORT_COPY:
            sub.operator("object.ml_modifier_copy",
                        text="", icon='DUPLICATE').modifier = active_mod.name

    # === Gizmo object settings ===
    if ob.type in {'CURVE', 'FONT', 'LATTICE', 'MESH', 'SURFACE'}:
        if (active_mod.type in modifier_categories.HAVE_GIZMO_PROPERTY
                or active_mod.type == 'UV_PROJECT'):
            gizmo_ob = get_gizmo_object_from_modifier(active_mod)

            sub = row.row(align=True)
            sub.alignment = 'RIGHT'
            sub.enabled = is_active_mod_local

            if not gizmo_ob:
                sub_sub = sub.row()
                sub_sub.scale_x = 4
                icon = pcoll['ADD_GIZMO']
                sub_sub.operator("object.ml_gizmo_object_add", text="", icon_value=icon.icon_id
                            ).modifier = active_mod.name
            else:
                sub_sub = sub.row(align=True)
                sub_sub.scale_x = 1.2
                depress = not gizmo_ob.hide_viewport
                sub_sub.operator("object.ml_gizmo_object_toggle_visibility", text="",
                                icon='EMPTY_ARROWS', depress=depress)
                sub.popover("OBJECT_PT_ml_gizmo_object_settings", text="")

    # === Modifier specific settings ===
    box = col.box()
    # Disable layout for linked modifiers here manually so in custom
    # layouts all operators/settings are greyed out.
    box.enabled = is_active_mod_local

    # A column is needed here to keep the layout more compact,
    # because in a box separators give an unnecessarily big space.
    col = box.column()

    # Some modifiers have an improved layout with additional settings.
    have_custom_layout = (
        'BOOLEAN',
        'LATTICE'
    )

    if active_mod.type in have_custom_layout:
        getattr(ml_modifier_layouts, active_mod.type)(col, ob, active_mod)
    else:
        mp = DATA_PT_modifiers(context)
        getattr(mp, active_mod.type)(col, ob, active_mod)
