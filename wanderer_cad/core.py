"""Wanderer CAD : Constantes, préférences, langue, unités, plan de construction, création des objets courbe."""

import bmesh
import bpy
import math
import numpy as np
import re
import time
from mathutils import Vector


TAU = 2.0 * math.pi
SNAP_RADIUS = 14.0  # pixels
MARKER_SCALE = 0.2  # part de l'échelle d'écran appliquée au carré d'accrochage (1 = proportionnel)
IDLE_TOOL = "dessin.selection_boite_tool"  # outil par défaut (Select / Move) retrouvé après une commande ou Échap
IDLE_FALLBACK = "builtin.select_box"

# Réglages des préférences de l'add-on (valeurs utilisées aussi quand les préférences sont inaccessibles)
PREF_DEFAULTS = {"light_preview": True, "curve_points": True, "rclick_enter": True, "cmd_line": True, "cmd_type": False, "cmd_size": 100, "mode_icons": False, "oda_path": "", "cmd_key": 'SPACE', "esc_deselect": True, "enter_last": True, "auto_idle": True, "smart_tracks": True, "gumball_rot90": True, "gumball_step": '90', "gumball_line": 3.0, "icon_palette": 'EARTH', "language": 'EN', "rich_tooltips": True, "remap_grs": False, "view_pan": True, "view_persp": True, "view_button": 'MIDDLE', "mouse_orbit": 'DEFAULT', "mouse_menu": 'DEFAULT', "mouse_middle": 'DEFAULT', "mouse_menu_tol": 6, "mouse_middle_op": "", "cursor_style": 'AUTOCAD', "cursor_size": 8, "cursor_pick": 2.0, "cursor_color": (1.0, 1.0, 1.0),
                 "nav_style": 'BLENDER', "nav_zoom_cursor": False, "nav_invert_zoom": False,
                 "nav_auto_depth": False, "nav_dblclick_all": False,
                 "show_tool_annotate": False, "show_tool_measure": False, "show_tool_cube": False, "show_tool_select": False, "show_tool_cursor": False, "show_tool_move": False,
                 "show_tool_rotate": False, "show_tool_scale": False, "show_tool_transform": False, "show_toolbar_tools": True,
                 "snap_budget": 2.0, "curve_quality": 'NORMAL', "far_warning": True}


def pref(name):
    try:
        return getattr(bpy.context.preferences.addons[__package__].preferences, name)
    except (KeyError, AttributeError, ReferenceError):
        return PREF_DEFAULTS[name]


_LAST_TYPED = {}     # dernière valeur saisie, par outil et par étape : Entrée sans rien taper la reprend (comme Rhino)


def last_typed(key):
    """Dernière valeur saisie pour cette clé (None si aucune, ou si la préférence est coupée)."""
    return _LAST_TYPED.get(key) if pref("enter_last") else None


def fmt_typed(v):
    return f"{v:.4f}".rstrip('0').rstrip('.') if isinstance(v, float) else str(v)


# ---- Langue du module (réglage dans les préférences ; s'applique au prochain démarrage de Blender) ----
FR_LABELS = {
    "Selection Filters": "Filtres de sélection",
    "Meshes": "Maillages",
    "Curves": "Courbes",
    "Text": "Texte",
    "Lights": "Lumières",
    "Cameras": "Caméras",
    "Empties / Blocks": "Vides / Blocs",
    "Point Clouds": "Nuages de points",
    "Others": "Autres",
    "Align": "Aligner", "Arc: 3 Points": "Arc : 3 points", "Arc: Center, Start, End": "Arc : centre, début, fin",
    "Area / Perimeter": "Aire / périmètre", "Area Light": "Lumière surfacique", "Array: Linear": "Réseau : linéaire",
    "Array: Polar": "Réseau : polaire", "Array: Rectangular": "Réseau : rectangulaire", "Blend Surface": "Raccord de surface",
    "Boolean Difference": "Différence booléenne", "Boolean Intersection": "Intersection booléenne",
    "Boolean Split": "Division booléenne", "Boolean Union": "Union booléenne", "Box": "Boîte", "Camera": "Caméra",
    "Camera with Target": "Caméra avec cible", "Cap": "Boucher", "Chamfer Edge": "Chanfrein d'arête", "Circle": "Cercle",
    "Circle: Center, Radius": "Cercle : centre, rayon", "Circle: Diameter": "Cercle : diamètre",
    "Circle: Diameter": "Cercle : diamètre", "Clear all shortcuts": "Effacer tous les raccourcis",
    "Command Line": "Ligne de commande", "Cone": "Cône", "Construction Line": "Ligne de construction",
    "Control Point Curve": "Courbe par points de contrôle", "Copy": "Copier",
    "Copy (base → destinations)": "Copier (base → destinations)", "Split": "Couper", "Cylinder": "Cylindre",
    "Delete All Dimensions": "Supprimer toutes les cotes", "Delete Named View": "Supprimer la vue nommée",
    "Deselect All": "Tout désélectionner", "Dimension": "Cote", "Dimension (measure)": "Cote (mesure)",
    "Divide": "Diviser", "Drawing": "Dessin", "Duplicate Named View": "Dupliquer la vue nommée",
    "Edge Surface": "Surface par arêtes", "Ellipse: By Corners": "Ellipse : par les coins",
    "Ellipse: Diameter": "Ellipse : diamètre", "Ellipse: From Center": "Ellipse : depuis le centre",
    "Ellipse: From Foci": "Ellipse : par les foyers", "Ellipsoid": "Ellipsoïde", "Explode": "Décomposer",
    "Extrude": "Extruder", "Extrude Curve": "Extruder la courbe", "Extrude Along Curve": "Extruder le long d'une courbe", "Extrude Surface": "Extruder une surface",
    "Fillet Edge": "Congé d'arête", "Clipping Plane": "Plan de coupe", "Fillet Curve": "Raccord", "Chamfer Curve": "Chanfrein", "Group": "Grouper", "Groups": "Groupes", "Join": "Joindre",
    "Lasso Select": "Sélection au lasso", "Leave the tool": "Quitter l'outil", "Loft": "Lissage", "Make 2D": "Créer le 2D",
    "Match Surface": "Adapter la surface", "Material": "Matériau", "Mirror": "Miroir", "Move": "Déplacer",
    "Move (base → destination)": "Déplacer (base → destination)", "Named Views": "Vues nommées",
    "Offset Edge": "Décaler l'arête", "Offset Surface": "Décaler la surface", "Overkill": "Nettoyer", "Inset": "Incruster", "SubD Loft": "Lissage SubD", "SubD Sweep 1": "Balayage SubD 1 rail", "SubD Sweep 2": "Balayage SubD 2 rails", "SubD Revolve": "Révolution SubD", "Through the curves": "Par les courbes", "Points per curve": "Points par courbe", "SubD Box": "Boîte SubD", "SubD Sphere": "Sphère SubD", "SubD Cylinder": "Cylindre SubD", "SubD Cone": "Cône SubD", "SubD Torus": "Tore SubD", "SubD Plane": "Plan SubD", "To SubD": "Vers SubD", "SubD to Mesh": "SubD vers maillage", "Toggle SubD Display": "Affichage SubD lisse / cage", "Crease": "Pli", "Remove Crease": "Retirer le pli", "Insert Edge": "Insérer une arête", "Slide": "Glisser", "Bridge": "Pont", "Fill": "Remplir", "Append Face": "Ajouter une face", "Merge Faces": "Fusionner les faces", "Weld": "Souder", "Stitch": "Coudre", "Extract Faces": "Extraire les faces", "Select Loop": "Sélectionner la boucle", "Select Ring": "Sélectionner l'anneau", "Symmetry X": "Symétrie X", "Symmetry Y": "Symétrie Y", "Symmetry Z": "Symétrie Z", "SubD faces": "Faces SubD", "Pipe radius": "Rayon des tubes", "ID Point": "Point ID", "Show Edges": "Afficher les arêtes",
    "Patch": "Remplissage", "Pick object": "Choisir un objet", "Planar Surface": "Surface plane", "Plane": "Plan",
    "Plane (first corner → opposite corner)": "Plan (premier coin → coin opposé)", "Point Light": "Lumière ponctuelle",
    "Polygon: Area": "Polygone : aire", "Polygon: Center, Radius": "Polygone : centre, rayon",
    "Polygon: Circumscribed": "Polygone : circonscrit", "Polygon: Edge": "Polygone : arête", "Polygon: Star": "Polygone : étoile",
    "Polyline": "Polyligne", "Polyline (point by point)": "Polyligne (point par point)", "Project Curve": "Projeter une courbe",
    "Pyramid": "Pyramide", "Radius / Diameter": "Rayon / diamètre", "Center Mark": "Marque de centre", "Hatch": "Hachure", "Untrim": "Désajuster", "Untrim Holes": "Désajuster les trous", "Block": "Bloc", "Insert Block": "Insérer un bloc", "Block Edit": "Éditer le bloc", "Close Block Edit": "Fermer l'édition du bloc", "Explode Block": "Décomposer le bloc", "Blocks": "Blocs", "Delete Block": "Supprimer le bloc", "Select Block Copies": "Sélectionner les copies du bloc", "No block yet": "Aucun bloc", "Rebuild Curve": "Reconstruire la courbe", "Simplify Curve": "Simplifier la courbe", "Change Degree": "Changer le degré", "Insert Control Point": "Insérer un point de contrôle", "Remove Control Point": "Supprimer un point de contrôle", "Match Curve": "Raccorder la courbe", "Blend Curve": "Courbe de raccord", "Network Surface": "Surface par réseau", "Fillet Surface": "Raccord de surfaces", "Chamfer Surface": "Chanfrein de surfaces", "Extend Surface": "Prolonger la surface", "Split at Isocurve": "Couper à l'isocourbe", "Continue Dimension": "Cote continue", "Ordinate Dimension": "Cote ordonnée", "Arc Length Dimension": "Cote de longueur d'arc", "Move Dimension Line": "Déplacer la ligne de cote", "Selected dimension": "Cote sélectionnée", "Hatch Region": "Hachure par point", "Hatch Base Point": "Point de base de hachure", "Explode Hatch": "Décomposer la hachure", "Hatch Boundary": "Contour de hachure", "Match Hatch": "Copier la hachure", "New hatches": "Nouvelles hachures", "Base Point": "Point de base", "Boundary": "Contour", "By Point": "Par point", "Rail Revolve": "Révolution sur rail",
    "Remove All Materials": "Supprimer tous les matériaux", "Rename Named View": "Renommer la vue nommée",
    "Reset to defaults": "Valeurs par défaut", "Restore Named View": "Restaurer la vue nommée", "Revolve": "Révolution",
    "Rotate": "Rotation", "Rotate (center, reference, angle)": "Rotation (centre, référence, angle)",
    "Save Current View": "Enregistrer la vue actuelle", "Scale": "Échelle", "Scale 1D": "Échelle 1D", "Scale 2D": "Échelle 2D",
    "Select": "Sélectionner",
    "Select Loop": "Sélectionner la boucle", "Shell": "Coque", "Show / Hide Tab": "Afficher / masquer l'onglet",
    "Sphere": "Sphère", "Split Face": "Diviser la face", "Spot Light": "Projecteur", "Stretch": "Étirer", "Sun Light": "Soleil",
    "Sweep 1 Rail": "Balayage 1 rail", "Sweep 2 Rails": "Balayage 2 rails", "Thicken": "Épaissir", "Torus": "Tore", "Track To": "Pointer vers", "Trim": "Ajuster",
    "Truncated Cone": "Cône tronqué", "Truncated Pyramid": "Pyramide tronquée", "Truncated Sphere": "Sphère tronquée",
    "Ungroup": "Dégrouper", "Update Named View": "Mettre à jour la vue nommée",
    # commandes générales
    "Undo": "Annuler", "Redo": "Rétablir", "Delete": "Supprimer", "Select All": "Tout sélectionner", "Select None": "Tout désélectionner",
    "Invert Selection": "Inverser la sélection", "Hide": "Masquer", "Isolate": "Isoler", "Show All": "Tout afficher",
    "Zoom Extents": "Zoom étendu", "Zoom Selected": "Zoom sur la sélection", "Perspective / Ortho": "Perspective / orthogonale",
    "Wireframe": "Filaire", "Shaded": "Ombré", "Rendered": "Rendu", "X-Ray": "Rayons X", "Grid": "Grille",
    "Cursor to Origin": "Curseur à l'origine", "Save": "Enregistrer", "Select Similar": "Sélectionner similaire",
    "Select Similar Material": "Sélectionner même matériau", "Select Similar Type": "Sélectionner même type",
    "Select Similar Collection": "Sélectionner même collection", "Select Similar Hierarchy": "Sélectionner la hiérarchie",
    "Select Similar Area": "Sélectionner même aire", "Select Similar Normal": "Sélectionner même normale",
    "Select Similar Sides": "Sélectionner même nombre de côtés", "Select Linked": "Sélectionner lié", "Sidebar": "Barre latérale",
    "Toolbar": "Barre d'outils", "Overlays": "Surcouches", "Statistics": "Statistiques", "Maximize Area": "Agrandir la zone",
    "Local View": "Vue locale", "Camera View": "Vue caméra", "Cursor to Selected": "Curseur sur la sélection",
    # vues
    "Top": "Dessus", "Front": "Face", "Right": "Droite", "Back": "Arrière", "Left": "Gauche", "Bottom": "Dessous",
    "Perspective": "Perspective",
}

FR_ALIASES = {
    "layout_detail_tool": "fenetre fmult detail",
    # alias de l'AutoCAD français (DP, CP, RI, EH, DC, AJ, E, DO, PO, L...) + noms français complets
    "deplacer_tool": "dp deplacer", "copier_tool": "cp copier", "selection_boite_tool": "selectionner", "selection_lasso_tool": "lasso", "selection_rect_tool": "selboite", "selection_cercle_tool": "selcercle",
    "polyligne_tool": "pl po l ligne polyligne", "plan_tool": "plan", "rotation_tool": "ri rotation pivoter",
    "echelle_tool": "eh echelle", "echelle_2d_tool": "echelle2d", "echelle_1d_tool": "echelle1d", "echelle_taille_tool": "echelletaille",
    "rectangle_tool": "rec rectangle", "mirror_tool": "mi miroir symetrie", "array_rect_tool": "re reseau reseaurect",
    "array_linear_tool": "reseaulin", "array_polar_tool": "reseaupol", "cut_tool": "couper scinder split", "fillet_edge_tool": "raccordarete conge",
    "chamfer_edge_tool": "chanfreinarete", "offset_edge_tool": "dc decaler", "bool_union_tool": "union",
    "bool_difference_tool": "soustraire difference", "bool_intersection_tool": "intersection", "bool_split_tool": "diviserbool",
    "poly_center_tool": "polygone", "cercle_tool": "c cercle", "cercle_diametre_tool": "cercled", "ellipse_centre_tool": "el ellipse",
    "arc_cse_tool": "a arc", "arc_3pts_tool": "arc3", "boite_tool": "boite", "cylindre_tool": "cyl cylindre", "cone_tool": "cone",
    "pyramide_tool": "pyramide", "tube_tool": "tube", "sphere_tool": "sphere", "tore_tool": "tore", "cotation_tool": "cote cotation",
    "cotation_rayon_tool": "coterayon", "mesure_aire_tool": "ai aire", "subd_loft_tool": "subdlissage", "subd_sweep1_tool": "subdbalayage1", "subd_sweep2_tool": "subdbalayage2", "subd_revolve_tool": "subdrevolution", "subd_box_tool": "subdboite", "subd_sphere_tool": "subdsphere", "subd_cylinder_tool": "subdcylindre", "subd_cone_tool": "subdcone", "subd_torus_tool": "subdtore", "subd_plane_tool": "subdplan", "text_tool": "texte tx dt", "center_mark_tool": "centremarque marquecentre centre", "hatch_tool": "h hachure hachures", "untrim_tool": "desajuster", "untrim_holes_tool": "desajustertrous", "block_tool": "bloc b", "block_insert_tool": "inserer i", "rebuild_crv_tool": "reconstruire", "simplify_crv_tool": "simplifier", "change_degree_tool": "changerdegre degre", "insert_point_tool": "insererpoint", "remove_point_tool": "supprimerpoint", "match_crv_tool": "raccordercourbe", "blend_crv_tool": "courbederaccord", "network_srf_tool": "surfacereseau", "fillet_srf_tool": "raccordsurface", "chamfer_srf_tool": "chanfreinsurface", "extend_srf_tool": "prolongersurface", "split_iso_tool": "couperiso", "cotation_chain_tool": "cotecontinue cotebase", "cotation_ordinate_tool": "coteordonnee", "cotation_arc_tool": "cotearc longueurarc", "cotation_edit_tool": "deplacercote", "hatch_region_tool": "hachurepoint hachurezone", "dist_tool": "di dist distance", "id_point_tool": "id coordonnees", "cotation_angle_tool": "cotangle cotationangle", "annotation_tool": "repere annotation", "curve_cp_tool": "courbe", "extrude_path_tool": "extrudersurcourbe", "srf_corners_tool": "surfacepoints srfpt", "curve_interp_tool": "interpoler courbeinterp", "sketch_tool": "croquis", "pen_tool": "plume bezier", "point_tool": "pt point", "trim_tool": "aj ajuster",
    "join_tool": "j joindre jonction", "explode_tool": "decomposer", "align_tool": "ali aligner", "make2d_tool": "creer2d", "revolve_tool": "revolution",
    "loft_tool": "lissage", "sweep1_tool": "balayage1", "sweep2_tool": "balayage2", "light_point_tool": "lumiere lumierepoint", "light_spot_tool": "projecteur",
    "light_sun_tool": "soleil", "light_area_tool": "lumieresurface", "camera_tool": "camera", "camera_target_tool": "cameracible",
    "offset_surface_tool": "decalersrf", "extrude_tool": "extruder", "extrude_crv_tool": "extrudercourbe", "extrude_srf_tool": "es extrudersrf",
    "planar_srf_tool": "surfaceplane", "edge_srf_tool": "surfacearete", "thicken_tool": "epaissir", "cap_tool": "boucher",
    "split_face_tool": "diviserface", "project_curve_tool": "projeter", "patch_tool": "remplissage", "blend_srf_tool": "raccordsrf",
    "match_srf_tool": "adapter", "rail_revolve_tool": "revolrail", "shell_tool": "coque", "xline_tool": "do droite",
    "stretch_tool": "e etirer", "divide_tool": "div me diviser mesurer", "overkill_tool": "nettoyer", "clip_plane_tool": "plancoupe plandecoupe clip", "fillet_curve_tool": "raccord", "chamfer_curve_tool": "chanfrein",
    "pipe_tool": "tuyau", "intersect_tool": "intersectionobjets", "section_tool": "coupe", "contour_tool": "contours",
    "extract_srf_tool": "extrairesrf", "dup_border_tool": "dupliquerbord dupliquerbordure", "dup_edge_tool": "dupliquerarete",
    "merge_faces_tool": "fusionnerfaces", "unroll_tool": "developper developpersrf", "rebuild_srf_tool": "reconstruiresrf",
    "orient_tool": "orienter",
}
FR_LABELS.update({
    "Pipe": "Tuyau", "Intersect": "Intersection d'objets", "Section": "Section", "Contour": "Contour",
    "Extract Surface": "Extraire une surface", "Duplicate Border": "Dupliquer la bordure", "Duplicate Edge": "Dupliquer une arête",
    "Merge All Faces": "Fusionner les faces coplanaires", "Unroll Surface": "Développer une surface",
    "Rebuild Surface": "Reconstruire une surface", "Orient": "Orienter",
})
FR_LABELS.update({
    "Layout": "Mise en page", "Layouts": "Mises en page", "New Layout": "Nouvelle mise en page", "Open Layout": "Ouvrir la mise en page",
    "Model": "Objet (modèle)", "Paper Space": "Espace papier", "Next Layout": "Mise en page suivante", "Rename Layout": "Renommer la mise en page",
    "Delete Layout": "Supprimer la mise en page", "Duplicate Layout": "Dupliquer la mise en page", "Page Setup": "Format du papier",
    "Viewport": "Fenêtre", "Viewports": "Fenêtres", "Add Viewport": "Ajouter une fenêtre", "Update Viewports": "Mettre à jour les fenêtres",
    "Fit Viewport": "Cadrer la fenêtre", "Viewport Scale": "Échelle de la fenêtre", "Pan Viewport": "Panoramique dans la fenêtre",
    "Viewport Grip": "Poignée de fenêtre", "Draw a Viewport": "Dessiner une fenêtre", "Display Locked": "Affichage verrouillé",
    "Use a Model View": "Utiliser une vue du modèle", "Hide / Show Layer in Viewport": "Masquer / afficher le calque dans la fenêtre",
    "Match Model Text Height": "Ajuster la hauteur de texte du modèle", "Layers in this Viewport": "Calques dans cette fenêtre",
    "Export PDF": "Exporter en PDF", "Export SVG": "Exporter en SVG", "Export DXF": "Exporter en DXF", "Page": "Page", "Print": "Impression",
})
FR_ACTION_ALIASES = {
    "Layout": "miseenpage presentation nouvellemiseenpage", "Model": "objet modele ongletobjet",
    "Next Layout": "miseenpagesuivante", "Paper Space": "papier espacepapier epapier", "Update Viewports": "majfenetres majdetails regen", "Viewport Scale": "echellefenetre echelledetail",
    "Fit Viewport": "cadrerfenetre cadrerdetail", "Pan Viewport": "eobjet espaceobjet panofenetre panodetail", "Page Setup": "formatpapier", "Export PDF": "imprimer tracer exporterpdf",
    "Export SVG": "exportersvg", "Export DXF": "exporterdxf",
    "Block Edit": "editerbloc modifbloc", "Close Block Edit": "fermerbloc", "Explode Block": "decomposerbloc", "Hatch Base Point": "basehachure", "Explode Hatch": "decomposerhachure", "Hatch Boundary": "contourhachure", "Match Hatch": "copierhachure",
    "Undo": "annuler", "Redo": "retablir", "Delete": "ef effacer supprimer", "Select All": "toutsel", "Select None": "toutdesel",
    "Invert Selection": "inverser", "Hide": "masquer", "Isolate": "isoler", "Show All": "toutafficher", "Zoom Extents": "z zoometendu",
    "Zoom Selected": "zoomsel", "Wireframe": "filaire", "Shaded": "ombre", "Rendered": "rendu", "Grid": "grille",
    "Save": "enregistrer", "Local View": "vuelocale", "Camera View": "vuecamera", "Group": "gr grouper", "Ungroup": "degrouper",
}

# phrases de l'invite de commande (traduites à l'affichage, après analyse du texte : l'ordre des segments ne change pas)
FR_PHRASES = (
    ("insertion point (bottom left of the text)", "point d'insertion (en bas à gauche du texte)"),
    ("type the text   (Enter: next line, Enter on an empty line: finish, Backspace: erase, Esc: finish)", "taper le texte   (Entrée : ligne suivante, Entrée sur une ligne vide : terminer, Retour arrière : effacer, Échap : terminer)"),
    ("Angle in plane", "Angle dans le plan"), ("From plane", "Depuis le plan"),
    ("From: base point", "From : point de base"), ("Esc: cancel From", "Échap : annuler From"), ("From: offset", "From : décalage"),
    ("type @x,y  @distance<angle  or a distance along the cursor, Enter", "taper @x,y  @distance<angle  ou une distance vers le curseur, Entrée"), ("Shift+F: From", "Maj+F : From"),
    ("Aligned", "Alignée"), ("Horizontal", "Horizontale"), ("Vertical", "Verticale"),
    ("first point of the cutting line (or click an existing line)", "premier point de la ligne de coupe (ou cliquer une ligne existante)"),
    ("first corner of the crossing window", "premier coin de la fenêtre de capture"),
    ("opposite corner of the window", "coin opposé de la fenêtre"),
    ("first corner of the unit cell", "premier coin de la cellule unité"),
    ("opposite corner of the unit cell", "coin opposé de la cellule unité"),
    ("first reference point (end of the reference length)", "premier point de référence (fin de la longueur de référence)"),
    ("second reference point (new length from the second base point), or type the length", "second point de référence (nouvelle longueur depuis le second point de base), ou taper la longueur"),
    ("second base point (where the first base point goes)", "second point de base (où va le premier point de base)"),
    ("second reference point", "second point de référence"),
    ("point the line goes through", "point de passage de la ligne"),
    ("click to place the target Empty (the camera looks at it)", "cliquer pour placer l'Empty cible (la caméra le regarde)"),
    ("click to place the camera (50 mm)", "cliquer pour placer la caméra (50 mm)"),
    ("click to set the direction (steps of 90°)", "cliquer pour fixer la direction (pas de 90°)"),
    ("click or drag a box to select the edges", "cliquer ou tracer une zone pour sélectionner les arêtes"),
    ("click the edges / a curve or drag a box", "cliquer les arêtes / une courbe ou tracer une zone"),
    ("click the corners of the contour", "cliquer les coins du contour"),
    ("click a circle or an arc", "cliquer un cercle ou un arc"),
    ("click to confirm", "cliquer pour valider"),
    ("move the mouse to choose the side and the distance, or type the distance", "déplacer la souris pour choisir le côté et la distance, ou taper la distance"),
    ("height: move the mouse or type the value then Enter", "hauteur : déplacer la souris ou taper la valeur puis Entrée"),
    ("middle of an edge", "milieu d'une arête"),
    ("start point (sets the radius)", "point de départ (fixe le rayon)"),
    ("target point (direction of the light)", "point cible (direction de la lumière)"),
    ("target point (where the spot aims)", "point cible (où vise le projecteur)"),
    ("end of the first axis", "fin du premier axe"), ("end of the second axis", "fin du deuxième axe"),
    ("end of the third axis (height)", "fin du troisième axe (hauteur)"),
    ("end of the mirror line", "fin de la ligne de miroir"), ("start of the mirror line", "début de la ligne de miroir"),
    ("end of the revolve axis", "fin de l'axe de révolution"), ("start of the revolve axis", "début de l'axe de révolution"),
    ("end of the edge", "fin de l'arête"), ("start of the edge", "début de l'arête"),
    ("end point", "point final"), ("start point", "point de départ"),
    ("second end of the first axis", "seconde extrémité du premier axe"), ("first end of the first axis", "première extrémité du premier axe"),
    ("first end of the diameter", "première extrémité du diamètre"), ("second end", "seconde extrémité"),
    ("second focus", "second foyer"), ("first focus", "premier foyer"),
    ("point on the arc", "point sur l'arc"), ("point on the ellipse", "point sur l'ellipse"),
    ("first control point", "premier point de contrôle"), ("next control point", "point de contrôle suivant"),
    ("first point to measure", "premier point à mesurer"),
    ("next corner", "coin suivant"), ("first corner", "premier coin"), ("opposite corner", "coin opposé"),
    ("dimension line position", "position de la ligne de cote"), ("position of the dimension", "position de la cote"),
    ("position of the camera (50 mm)", "position de la caméra (50 mm)"), ("position of the light", "position de la lumière"),
    ("position of the spot", "position du projecteur"), ("position of the sun", "position du soleil"),
    ("destination point", "point de destination"), ("destination", "destination"),
    ("base center", "centre de base"), ("base point", "point de base"), ("center of rotation", "centre de rotation"),
    ("center of the polar array", "centre du réseau polaire"),
    ("cut height from the center", "hauteur de coupe depuis le centre"),
    ("radius of the cone at the target (drag, or type the radius then Enter)", "rayon du cône à la cible (glisser, ou taper le rayon puis Entrée)"),
    ("radius (drag, or type the radius then Enter)", "rayon (glisser, ou taper le rayon puis Entrée)"),
    ("major radius", "grand rayon"), ("outer radius", "rayon extérieur"), ("second radius (inside or outside the first)", "second rayon (dans ou hors du premier)"), ("invalid second radius", "second rayon invalide"), ("Invalid shape", "Forme invalide"), ("inner radius", "rayon intérieur"),
    ("top radius", "rayon supérieur"), ("tube radius", "rayon du tube"), ("radius", "rayon"),
    ("area and perimeter of the selection", "aire et périmètre de la sélection"),
    ("angle (type then Enter) or first reference point", "angle (taper puis Entrée) ou premier point de référence"),
    ("factor (type then Enter) or first reference point", "facteur (taper puis Entrée) ou premier point de référence"),
    ("angle: type degrees then Enter, or Enter / click for 360°", "angle : taper les degrés puis Entrée, ou Entrée / clic pour 360°"),
    ("vertex", "sommet"), ("direction", "direction"), ("height", "hauteur"), ("center", "centre"),
    ("second point", "second point"), ("first point", "premier point"), ("next point", "point suivant"),
    ("type the distance", "taper la distance"), ("type the radius", "taper le rayon"),
    ("or type the radius then Enter", "ou taper le rayon puis Entrée"), ("or type the length then Enter", "ou taper la longueur puis Entrée"),
    ("or type the angle in degrees then Enter", "ou taper l'angle en degrés puis Entrée"),
    ("or type the angle then Enter", "ou taper l'angle puis Entrée"), ("or type the diameter then Enter", "ou taper le diamètre puis Entrée"),
    ("or type the chord length then Enter", "ou taper la longueur de corde puis Entrée"),
    ("or type the area then Enter", "ou taper l'aire puis Entrée"),
    ("or type the inner radius then Enter", "ou taper le rayon intérieur puis Entrée"),
    ("or type the distance between the foci then Enter", "ou taper la distance entre les foyers puis Entrée"),
    ("or type the total length of the main axis then Enter", "ou taper la longueur totale du grand axe puis Entrée"),
    ("or type the length then Enter", "ou taper la longueur puis Entrée"),
    ("or type the length", "ou taper la longueur"),
    ("or type, then Enter", "ou taper, puis Entrée"),
    ("or type the radius, Tab, the height, Enter", "ou taper le rayon, Tab, la hauteur, Entrée"),
    ("Shift: orthogonal, or type the distance then Enter; Enter/Esc: finish", "Maj : orthogonal, ou taper la distance puis Entrée ; Entrée/Échap : terminer"),
    ("Shift: orthogonal, or type the distance then Enter", "Maj : orthogonal, ou taper la distance puis Entrée"),
    ("Shift: orthogonal, or type the length then Enter", "Maj : orthogonal, ou taper la longueur puis Entrée"),
    ("Shift: orthogonal, or type the angle in degrees then Enter", "Maj : orthogonal, ou taper l'angle en degrés puis Entrée"),
    ("Shift: orthogonal", "Maj : orthogonal"), ("Shift: free aim", "Maj : visée libre"),
    ("Shift: 15° steps", "Maj : pas de 15°"), ("Shift: circle", "Maj : cercle"), ("Shift: square", "Maj : carré"),
    ("Shift: cube", "Maj : cube"),
    ("or type the height then Enter", "ou taper la hauteur puis Entrée"),
    ("or type the spacing then Enter", "ou taper l'espacement puis Entrée"),
    ("or type c then Enter", "ou taper c puis Entrée"),
    ("or type the value then Enter", "ou taper la valeur puis Entrée"),
    ("type width, Tab, height, Enter", "taper la largeur, Tab, la hauteur, Entrée"),
    ("type width, Tab, depth, Tab, height, Enter", "taper la largeur, Tab, la profondeur, Tab, la hauteur, Entrée"),
    ("type count, Tab, spacing, Enter", "taper le nombre, Tab, l'espacement, Entrée"),
    ("type count, Tab, angle, Enter", "taper le nombre, Tab, l'angle, Entrée"),
    ("type counts with Tab", "taper les nombres avec Tab"),
    ("arrows: ←→ X count, ↑↓ Y count, PgUp/PgDn Z count", "flèches : ←→ nombre en X, ↑↓ nombre en Y, PgUp/PgDn nombre en Z"),
    ("Backspace: undo last point", "Retour arrière : annuler le dernier point"), ("Enter: finish", "Entrée : terminer"),
    ("click the first point: close", "cliquer le premier point : fermer"),
    ("click the first point, or Enter: close and measure", "cliquer le premier point, ou Entrée : fermer et mesurer"),
    ("box to the right: inside, to the left: touching, Ctrl/Cmd: deselect, click a selected edge: remove it",
     "zone vers la droite : à l'intérieur, vers la gauche : au contact, Ctrl/Cmd : désélectionner, cliquer une arête sélectionnée : la retirer"),
    ("box to the right: inside, to the left: touching, Ctrl/Cmd: deselect", "zone vers la droite : à l'intérieur, vers la gauche : au contact, Ctrl/Cmd : désélectionner"),
    ("number of sides", "nombre de côtés"), ("↑/↓: segments", "↑/↓ : segments"),
    ("D: 3D / 2D / 1D", "D : 3D / 2D / 1D"), ("D: spacing / total length", "D : espacement / longueur totale"),
    ("D: keep both parts", "D : garder les deux parties"), ("D: keep one side", "D : garder un côté"),
    ("D: keep the other side", "D : garder l'autre côté"), ("keep both parts", "garder les deux parties"),
    ("keep one side", "garder un côté"), ("keep the other side", "garder l'autre côté"),
    ("F: swap sides", "F : inverser les côtés"), ("F: other direction", "F : autre direction"), ("F: other side", "F : autre côté"),
    ("F: flip direction", "F : inverser la direction"), ("F: flip the light direction", "F : inverser la direction de la lumière"),
    ("C: copy / replace", "C : copier / remplacer"), ("C: from center", "C : depuis le centre"), ("R: free reference", "R : référence libre"), ("R: reference by two points", "R : référence par deux points"), ("R: reference / free reference", "R : référence / référence libre"), ("R: next mode", "R : mode suivant"), ("R: back to normal", "R : retour au mode normal"), ("reference angle: first point", "angle de référence : premier point"), ("reference angle: second point", "angle de référence : second point"), ("new angle: point, or type the angle then Enter", "nouvel angle : point, ou taper l'angle puis Entrée"), ("reference length: first point", "longueur de référence : premier point"), ("reference length: second point", "longueur de référence : second point"), ("new length: point (distance from the base point), or type the length then Enter", "nouvelle longueur : point (distance depuis le point de base), ou taper la longueur puis Entrée"), ("R: reference", "R : référence"),
    ("R: back to normal", "R : retour à la normale"),
    ("C: cap the ends", "C : boucher les extrémités"), ("D: delete the input", "D : supprimer l'entrée"),
    ("Esc: cancel", "Échap : annuler"), ("Enter/Space: quit", "Entrée/Espace : quitter"), ("Enter/Space: confirm", "Entrée/Espace : valider"),
    ("Esc: exit", "Échap : sortir"), ("Esc: leave", "Échap : quitter"),
    ("X/Y/Z: lock axis", "X/Y/Z : verrouiller l'axe"), ("X/Y/Z: change axis, same key: release", "X/Y/Z : changer d'axe, même touche : relâcher"),
    ("S: snap ON", "S : accrochage ON"), ("S: snap OFF", "S : accrochage OFF"), ("snap ON", "accrochage ON"), ("snap OFF", "accrochage OFF"),
    ("select the objects", "sélectionner les objets"), ("select the vertices", "sélectionner les sommets"),
    ("click: add, drag: box, Shift+click: toggle, Ctrl/Cmd+click: remove, A: all",
     "clic : ajouter, glisser : zone, Maj+clic : basculer, Ctrl/Cmd+clic : retirer, A : tout"),
    ("Select the solids to split first", "Sélectionner d'abord les solides à couper"),
    ("tracking:", "repérage :"), ("typed:", "saisi :"), ("Segment", "Segment"), ("Total", "Total"),
    ("selected", "sélectionné(s)"), ("copie(s)", "copie(s)"),
    ("(copy)", "(copie)"), ("[C: copy]", "[C : copier]"), ("1 copy", "1 copie"), ("copies", "copies"), ("Factor", "Facteur"),
    ("Type a command", "Taper une commande"), ("repeat ", "répéter "), ("Command", "Commande"), ("cancel", "annuler"),
    ("quit", "quitter"), ("leave", "quitter"), ("confirm", "valider"), ("run", "lancer"),
    ("selecting", "sélection"), ("replace", "remplacer"), ("copy", "copier"), ("count", "nombre"),
    # indications de la barre d'outils (dessin_hint)
    ("Click the curves to divide (or select them first)", "Cliquer les courbes à diviser (ou les sélectionner d'abord)"),
    ("Click the objects to clean (or select them first)", "Cliquer les objets à nettoyer (ou les sélectionner d'abord)"),
    ("Enter / Space: live preview, wheel or typed number of segments", "Entrée / Espace : aperçu en direct, molette ou nombre de segments saisi"),
    ("Enter / Space: tolerance and options", "Entrée / Espace : tolérance et options"),
    ("Two corners of the crossing window", "Deux coins de la fenêtre de capture"), ("base point, destination", "point de base, destination"),
    ("type the distance + Enter", "taper la distance + Entrée"), ("type the angle in degrees + Enter", "taper l'angle en degrés + Entrée"),
    ("Point, then direction", "Point, puis direction"), ("Solids", "Solides"),
    ("line of the cutting plane (two points, or click an existing line)", "ligne du plan de coupe (deux points, ou cliquer une ligne existante)"),
    ("Click the surface, then the curves on it", "Cliquer la surface, puis les courbes dessus"),
    ("Click the curves, then the surface(s) to project onto", "Cliquer les courbes, puis la ou les surfaces de projection"),
    ("Click the closed curves", "Cliquer les courbes fermées"),
    ("Select the surfaces first, Enter", "Sélectionner d'abord les surfaces, Entrée"),
    ("Enter / Space: patch", "Entrée / Espace : remplir"), ("Enter / Space: split", "Entrée / Espace : diviser"),
    ("Enter / Space: project", "Entrée / Espace : projeter"), ("Enter / Space", "Entrée / Espace"),
    ("Esc: leave", "Échap : quitter"),
    ("or type ", "ou taper "), ("or taper ", "ou taper "), ("then Enter", "puis Entrée"), ("(type ", "(taper "), ("[type ", "[taper "), ("Enter to confirm", "Entrée pour valider"),
    ("type the", "taper le"), ("type a", "taper a"),
    # commandes « on désigne les objets, puis Entrée » : indications et messages de la barre de commande
    ("click the curves first, then Enter", "cliquer d'abord les courbes, puis Entrée"),
    ("click at least two objects (surfaces, solids or curves), then Enter",
     "cliquer au moins deux objets (surfaces, solides ou courbes), puis Entrée"),
    ("the selected objects do not intersect", "les objets sélectionnés ne se coupent pas"),
    ("click the surfaces first, then Enter", "cliquer d'abord les surfaces, puis Entrée"),
    ("click the surface first, then Enter", "cliquer d'abord la surface, puis Entrée"),
    ("click the solids or surfaces first, then Enter", "cliquer d'abord les solides ou les surfaces, puis Entrée"),
    ("a closed solid has no free border", "un solide fermé n'a pas de bord libre"),
    ("use Duplicate Edge (DupEdge) to copy one of its edges", "utiliser Dupliquer une arête (DupEdge) pour copier une de ses arêtes"),
    ("no coplanar faces to merge", "aucune face coplanaire à fusionner"),
    ("Select the surfaces, solids or curves to cut first", "Sélectionner d'abord les surfaces, solides ou courbes à couper"),
    ("the plane does not cross the selected objects", "le plan ne traverse pas les objets sélectionnés"),
    ("no plane crosses the selected objects", "aucun plan ne traverse les objets sélectionnés"),
    ("Click two objects or more", "Cliquer au moins deux objets"), ("Click the surfaces", "Cliquer les surfaces"),
    ("Click the surface", "Cliquer la surface"), ("Click the curves", "Cliquer les courbes"), ("Click the objects", "Cliquer les objets"),
    ("Enter / Space: border curves", "Entrée / Espace : courbes de bordure"),
    ("Enter / Space: radius and options", "Entrée / Espace : rayon et options"),
    ("Enter / Space: intersection curves", "Entrée / Espace : courbes d'intersection"),
    ("Enter / Space: merge coplanar faces", "Entrée / Espace : fusionner les faces coplanaires"),
    ("Enter / Space: unroll", "Entrée / Espace : développer"),
    ("Enter / Space: point counts U and V", "Entrée / Espace : nombre de points en U et V"),
    # accrochage ponctuel (Maj + clic), Grid Snap
    ("One-shot snap", "Accrochage ponctuel"), ("only, for the next point", "uniquement, pour le prochain point"),
    ("one shot", "ponctuel"),
    ("start a command first, it applies to the next point picked", "lancer d'abord une commande : il vaut pour le prochain point désigné"),
    ("Shift + click: one shot (next point only)", "Maj + clic : accrochage ponctuel (prochain point seulement)"),
    ("All On", "Tout cocher"), ("All Off", "Tout décocher"), ("Disable (F3)", "Désactiver (F3)"),
    ("Grid Snap On (F9)", "Accrochage à la grille activé (F9)"), ("Grid Snap Off", "Accrochage à la grille désactivé"),
    ("Snap spacing", "Pas de l'accrochage"), ("Custom...", "Autre valeur..."), ("Spacing", "Pas"),
)
_FR_SORTED = tuple(sorted(FR_PHRASES, key=lambda p: -len(p[0])))
_TR_CACHE = {}


def lang():
    return pref("language")


_LANG_APPLIED = {"v": None}


def pref_applied_language():
    return _LANG_APPLIED["v"] or 'EN'


def tr_label(label):
    """Nom d'une commande ou d'un outil dans la langue du module."""
    return FR_LABELS.get(label, label) if lang() == 'FR' else label


def tr_text(txt):
    """Texte d'invite dans la langue du module (phrases connues remplacées, le reste inchangé)."""
    if not txt or lang() != 'FR':
        return txt
    v = _TR_CACHE.get(txt)
    if v is None:
        v = FR_LABELS.get(txt)
        if v is None:
            v = txt
            for en, fr in _FR_SORTED:
                if en in v:
                    v = re.sub(r"(?<![A-Za-zÀ-ÿ])" + re.escape(en) + r"(?![A-Za-zÀ-ÿ])", lambda _m, fr=fr: fr, v)
        if len(_TR_CACHE) > 4000:
            _TR_CACHE.clear()
        _TR_CACHE[txt] = v
    return v


def apply_language(classes_iter):
    """Au démarrage : noms français des outils, opérateurs et menus (bl_label ; l'original reste dans dessin_en_label)."""
    if lang() != 'FR':
        return
    for cls in classes_iter:
        try:
            en = cls.__dict__.get("dessin_en_label", getattr(cls, "bl_label", ""))
            fr = FR_LABELS.get(en)
            if fr and en:
                cls.dessin_en_label = en
                cls.bl_label = fr
        except (AttributeError, TypeError):
            continue


def idle_tool():
    """Retrouve l'outil Select / Move (sauf si le réglage « Return to Select / Move » est désactivé)."""
    if pref("auto_idle"):
        bpy.ops.wm.tool_set_by_id(name=IDLE_TOOL)

# 0 = Fin, 1 = Milieu, 2 = Centre, 3 = Origine
TRACK_RADIUS = 10.0     # px : distance d'attraction vers une ligne de repérage
TRACK_DWELL = 0.5       # s : survol d'un point d'accrochage pour l'« acquérir »
TRACK_MAX = 4           # points acquis simultanément
TRACK_COLORS = ((1.0, 0.35, 0.35, 0.9), (0.4, 0.85, 0.4, 0.9), (0.45, 0.65, 1.0, 0.9))
AXES3 = (Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0)))
SNAP_NAMES = {0: "End", 1: "Midpoint", 2: "Center", 3: "Point", 4: "Vertex", 5: "Quadrant", 6: "Knot",
              7: "Near", 8: "Intersection", 9: "Perpendicular", 10: "Tangent"}
SNAP_BIAS_LUT = np.array([0.0, 3.0, 0.0, 1.0, 0.0, 1.0, 1.0])     # points précalculés (types 0 à 6)
KIND_OSNAP = {0: "end", 1: "mid", 2: "cen", 3: "point", 4: "vertex", 5: "quad", 6: "knot"}
OSNAP_DEFAULTS = {"end": True, "near": True, "point": True, "mid": True, "cen": True, "int": True, "perp": False,
                  "tan": False, "quad": True, "knot": False, "vertex": True, "project": False, "disable": False}
SNAP_COLORS = {
    0: (0.2, 1.0, 0.3, 1.0),
    1: (0.3, 0.8, 1.0, 1.0),
    2: (1.0, 0.4, 0.9, 1.0),
    3: (1.0, 1.0, 1.0, 1.0),
    4: (1.0, 0.9, 0.2, 1.0),
    5: (1.0, 0.6, 0.1, 1.0),
    6: (0.6, 1.0, 0.6, 1.0),
    7: (0.8, 0.5, 1.0, 1.0),
    8: (1.0, 0.3, 0.3, 1.0),
    9: (0.4, 0.6, 1.0, 1.0),
    10: (1.0, 0.7, 0.3, 1.0),
}
HEAVY_SNAP_VERTS = 8000    # au-delà : accrochage allégé (un sommet par cellule)
HEAVY_SNAP_VERTS_EDIT = 120000   # objet en cours d'édition : tous ses sommets restent accrochables, c'est lui qu'on retouche
EDGE_CAP = 300000       # arêtes gardées pour Near / Int / Perp
DETAIL_SNAP_VERTS = 150000    # détail chargé sous le curseur : tous les sommets, milieux et arêtes jusqu'à cette taille
DETAIL_EDGE_CAP = 600000      # ... et jusqu'à ce nombre d'arêtes ; au-delà, un échantillon fin (grille 64³)


# ---- Accrochage ponctuel (« one shot », comme Rhino) : pendant qu'une commande demande un point, Maj tenu au-dessus des
# cases OSnap les montre toutes décochées ; Maj + clic sur une ou plusieurs cases : elles seules agissent pour le prochain
# point, à la place des accrochages cochés (même coupés par F3) ; puis tout revient. Maj relâché sans clic : rien ne change.
ONESHOT_KEYS = ("end", "near", "point", "mid", "cen", "int", "perp", "tan", "quad", "knot", "vertex")
ONESHOT_HOLD_MAX = 20.0          # s : garde-fou si le relâchement de Maj n'a pas été vu (fenêtre quittée touche enfoncée)
_ONESHOT = {"keys": (), "hold": False, "hold_t": 0.0}


def oneshot_keys():
    """Accrochages ponctuels armés, dans l'ordre de la barre : ("end", "mid")... ; vide s'il n'y en a pas."""
    return _ONESHOT["keys"]


def oneshot_hold():
    """Maj est tenu au-dessus des cases OSnap (elles paraissent décochées en attendant un clic)."""
    if _ONESHOT["hold"] and time.monotonic() - _ONESHOT["hold_t"] > ONESHOT_HOLD_MAX:
        _ONESHOT["hold"] = False
    return _ONESHOT["hold"]


def oneshot_shown():
    """Les cases montrent l'accrochage ponctuel (et non les réglages cochés)."""
    return bool(_ONESHOT["keys"]) or oneshot_hold()


def osnap_shown(st, key):
    """État affiché de la case d'un accrochage : Maj tenu ou accrochage ponctuel armé, seuls les ponctuels sont cochés."""
    if key in ONESHOT_KEYS and oneshot_shown():
        return key in _ONESHOT["keys"]
    return bool(getattr(st, "osnap_" + key))


def oneshot_set(keys):
    """Arme ces accrochages ponctuels (une clé ou plusieurs) ; les clés inconnues sont ignorées."""
    if isinstance(keys, str):
        keys = (keys,)
    want = set(keys or ())
    _ONESHOT["keys"] = tuple(k for k in ONESHOT_KEYS if k in want)


def oneshot_toggle(key):
    """Maj + clic sur une case : l'ajoute aux accrochages ponctuels, ou l'en retire. Retourne ceux qui restent armés."""
    if key in ONESHOT_KEYS:
        cur = set(_ONESHOT["keys"])
        cur.symmetric_difference_update({key})
        _ONESHOT["keys"] = tuple(k for k in ONESHOT_KEYS if k in cur)
    return _ONESHOT["keys"]


def oneshot_hold_set(on):
    """Maj tenu / relâché au-dessus des cases. True si l'état a changé (les barres sont redessinées)."""
    on = bool(on)
    if on:
        _ONESHOT["hold_t"] = time.monotonic()
    if on == _ONESHOT["hold"]:
        return False
    _ONESHOT["hold"] = on
    redraw_bars()
    return True


def oneshot_clear():
    """Fin de l'accrochage ponctuel ; True s'il y en avait un (les barres sont alors redessinées)."""
    if not _ONESHOT["keys"]:
        return False
    _ONESHOT["keys"] = ()
    redraw_bars()
    return True


def oneshot_reset():
    """Plus d'accrochage ponctuel ni de Maj tenu (fin de commande, clic simple sur une case)."""
    had = bool(_ONESHOT["keys"]) or _ONESHOT["hold"]
    _ONESHOT["keys"] = ()
    _ONESHOT["hold"] = False
    if had:
        redraw_bars()
    return had


def statusbar_redraw():
    """Fait redessiner la barre d'état. C'est une zone de la fenêtre, absente de screen.areas : on ne peut pas la marquer
    comme les autres ; reposer son texte (vide) la fait redessiner."""
    try:
        ws = bpy.context.workspace
        if ws is not None and bpy.context.window is not None:
            ws.status_text_set_internal(None)
    except (AttributeError, RuntimeError, ReferenceError, TypeError):
        pass


def redraw_bars():
    """Redessine les vues (barre de modes) et la barre d'état (cases OSnap)."""
    _redraw_all_areas()
    statusbar_redraw()


def mouse_over_statusbar(context, event):
    """La souris est sur la barre d'état de Blender (la bande sous toutes les zones de la fenêtre), où sont les cases OSnap."""
    try:
        win = context.window
        ymin = min(a.y for a in win.screen.areas)
        return 0 <= event.mouse_y < ymin and 0 <= event.mouse_x <= win.width
    except (AttributeError, ReferenceError, TypeError, ValueError):
        return False


def osnap(name):
    """Réglage OSnap de la scène (panneau OSnap) ; valeur par défaut si la scène n'est pas accessible.
    Accrochages ponctuels armés : eux seuls répondent oui (« project » garde son réglage, « disable » est ignoré)."""
    one = _ONESHOT["keys"]
    if one and name != "project":
        return name in one
    try:
        return getattr(bpy.context.scene.dessin, "osnap_" + name)
    except (AttributeError, ReferenceError):
        return OSNAP_DEFAULTS[name]

UNIT_TO_M = {
    'METERS': 1.0, 'CENTIMETERS': 0.01, 'MILLIMETERS': 0.001, 'KILOMETERS': 1000.0,
    'MICROMETERS': 1e-6, 'INCHES': 0.0254, 'FEET': 0.3048, 'MILES': 1609.344,
    'THOU': 2.54e-5, 'ADAPTIVE': 1.0,
}
UNIT_LABEL = {
    'METERS': 'm', 'CENTIMETERS': 'cm', 'MILLIMETERS': 'mm', 'KILOMETERS': 'km',
    'MICROMETERS': 'µm', 'INCHES': 'in', 'FEET': 'ft', 'MILES': 'mi',
    'THOU': 'thou', 'ADAPTIVE': 'm',
}

NAV_TYPES = {
    'MIDDLEMOUSE', 'RIGHTMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
    'WHEELINMOUSE', 'WHEELOUTMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM',
    'MOUSEROTATE', 'MOUSESMARTZOOM',
}


# --------------------------------------------------------------------------
# Utilitaires géométriques
# --------------------------------------------------------------------------

def unit_info(scene):
    """Retourne (unités Blender par unité affichée, libellé)."""
    us = scene.unit_settings
    if us.system == 'NONE':
        return 1.0, ""
    scale = us.scale_length if us.scale_length else 1.0
    key = us.length_unit
    return UNIT_TO_M.get(key, 1.0) / scale, UNIT_LABEL.get(key, "")


# ---- Accrochage à la grille (Grid Snap, F9, comme Rhino) ----
GRID_SNAP_PRESETS = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 500.0, 1000.0)     # en unités affichées
GRID_SNAP_DEFAULT_M = 0.1        # pas par défaut : 10 cm (le réglage scene.dessin.grid_snap_step est une longueur en mètres)


def unit_metres(scene):
    """Mètres par unité affichée de la scène (1 quand la scène n'a pas de système d'unités)."""
    us = scene.unit_settings
    return 1.0 if us.system == 'NONE' else UNIT_TO_M.get(us.length_unit, 1.0)


def grid_snap_shown(scene):
    """Pas de Grid Snap écrit dans l'unité affichée de la scène : 10 cm se lit 100 en mm, 10 en cm, 0.1 en m."""
    return float(f"{float(scene.dessin.grid_snap_step) / unit_metres(scene):.7g}")


def grid_snap_store(scene, shown):
    """Règle le pas de Grid Snap à partir d'une valeur lue dans l'unité affichée (menu, boîte de saisie)."""
    scene.dessin.grid_snap_step = float(shown) * unit_metres(scene)


def grid_snap_step(context=None):
    """Pas de l'accrochage à la grille en unités Blender ; 0 si Grid Snap est coupé. Le réglage est une longueur réelle
    (10 cm par défaut) : changer l'unité affichée de la scène ne change pas le pas, seulement la façon de l'écrire."""
    try:
        sc = (context or bpy.context).scene
        st = sc.dessin
        if not st.grid_snap:
            return 0.0
        step = grid_snap_shown(sc) * unit_info(sc)[0]
        return float(f"{step:.7g}")       # (les réglages de Blender sont en simple précision : 4,9999998 redevient 5)
    except (AttributeError, ReferenceError, TypeError, ValueError):
        return 0.0


def grid_snap_point(p, axis, step):
    """Point p ramené sur le nœud de grille le plus proche : la grille est celle du plan de construction (origine et
    axes du plan), de pas step. La hauteur de p au-dessus du plan ne change pas."""
    if step <= 0.0:
        return p
    u, v, n = plane_axes(axis)
    o = plane_origin(axis)
    d = p - o
    return o + u * (round(d.dot(u) / step) * step) + v * (round(d.dot(v) / step) * step) + n * d.dot(n)


def grid_snap_len(h, step):
    """Longueur (hauteur d'une boîte, d'une extrusion...) ramenée au multiple du pas le plus proche."""
    if h is None or step <= 0.0:
        return h
    return round(h / step) * step


# ---- Plan de construction (CPlane) : un plan par zone 3D ; sans plan personnalisé, on garde le plan XY / celui de la vue orthogonale ----
_CPLANE = {"cur": None}           # repère lu par plane_axes() quand axis == 3 (celui de la zone 3D qui dessine)
CPLANES = {}                      # rv3d.as_pointer() -> {"cur": (o, x, y, z) ou None, "hist": [], "redo": [], "side": bool}


def cp_state(rv3d, create=False):
    key = rv3d.as_pointer()
    st = CPLANES.get(key)
    if st is None and create:
        st = CPLANES[key] = {"cur": None, "hist": [], "redo": [], "side": False}
    return st


def cp_frame(o, x, y):
    """Repère direct (o, x, y, z) à partir d'une origine et de deux directions (y est rendu orthogonal à x)."""
    x = Vector(x).normalized()
    y = Vector(y) - x * Vector(y).dot(x)
    if y.length < 1e-9:
        return None
    y.normalize()
    return (Vector(o), x, y, x.cross(y).normalized())


def cp_set(rv3d, frame, record=True, auto=False):
    """Définit (ou, avec None, efface) le plan de construction de cette zone 3D. auto : posé par l'Auto CPlane."""
    st = cp_state(rv3d, create=True)
    if record:
        st["hist"].append(st["cur"])
        del st["hist"][:-30]
        st["redo"].clear()
    st["cur"] = frame
    st["auto"] = bool(auto and frame is not None)
    try:
        st["side"] = bool(rv3d.is_orthographic_side_view)
    except (AttributeError, ReferenceError):
        st["side"] = False


def cp_undo(rv3d):
    st = cp_state(rv3d)
    if not st or not st["hist"]:
        return False
    st["redo"].append(st["cur"])
    st["cur"] = st["hist"].pop()
    return True


def cp_redo(rv3d):
    st = cp_state(rv3d)
    if not st or not st["redo"]:
        return False
    st["hist"].append(st["cur"])
    st["cur"] = st["redo"].pop()
    return True


CP_WORLD = {   # plans du monde (Top = plan XY d'origine : on efface simplement le plan personnalisé)
    "Top": None,
    "Bottom": ((0, 0, 0), (1, 0, 0), (0, -1, 0)),
    "Front": ((0, 0, 0), (1, 0, 0), (0, 0, 1)),
    "Back": ((0, 0, 0), (-1, 0, 0), (0, 0, 1)),
    "Right": ((0, 0, 0), (0, 1, 0), (0, 0, 1)),
    "Left": ((0, 0, 0), (0, -1, 0), (0, 0, 1)),
}


def plane_axes(axis):
    """Axes (u, v, normale) du plan de construction pour une normale X/Y/Z (3 : plan personnalisé, voir CPlane)."""
    if axis == 3 and _CPLANE["cur"] is not None:
        _o, x, y, z = _CPLANE["cur"]
        return x.copy(), y.copy(), z.copy()
    if axis == 0:
        return Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0))
    if axis == 1:
        return Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, 1, 0))
    return Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def plane_origin(axis):
    if axis == 3 and _CPLANE["cur"] is not None:
        return _CPLANE["cur"][0].copy()
    return Vector((0.0, 0.0, 0.0))


def drawing_axis(rv3d):
    """Plan personnalisé (CPlane) -> 3. Sinon vue Top/Bottom -> Z, Front/Back -> Y, Right/Left -> X, et plan XY ailleurs."""
    st = cp_state(rv3d)
    if st is not None and st["cur"] is not None:
        if rv3d.is_orthographic_side_view and not st["side"]:
            st["cur"] = None                 # on est passé en vue Top / Front / Right : on retrouve le plan de cette vue
        else:
            _CPLANE["cur"] = st["cur"]
            return 3
    if rv3d.is_orthographic_side_view:
        d = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
        return max(range(3), key=lambda i: abs(d[i]))
    return 2


def arc_samples(c, u, v, r, t0, sweep, seg=64):
    n = max(2, int(abs(sweep) / TAU * seg) + 2)
    pts = []
    for i in range(n + 1):
        t = t0 + sweep * i / n
        pts.append(c + (u * math.cos(t) + v * math.sin(t)) * r)
    return pts


def arc_bezier_data(c, u, v, r, t0, sweep):
    """Liste de (position, handle_gauche, handle_droit) pour un arc en Bézier."""
    # un segment de Bézier par 45° au plus : l'écart au cercle vrai tombe à 0,0004 % du rayon (4 µm pour 1 m), contre
    # 0,027 % (0,27 mm pour 1 m) avec les 4 segments de 90° habituels. Un cercle a 8 points de contrôle, comme dans Rhino.
    n = max(1, int(math.ceil(abs(sweep) / (math.pi / 4.0) - 1e-9)))
    phi = sweep / n
    h = 4.0 / 3.0 * math.tan(phi / 4.0) * r
    out = []
    for i in range(n + 1):
        t = t0 + i * phi
        ct, st = math.cos(t), math.sin(t)
        pos = c + (u * ct + v * st) * r
        tan = -u * st + v * ct
        out.append((pos, pos - tan * h, pos + tan * h))
    return out


def circle_through_origin(b, p):
    """Centre (2D) du cercle passant par (0,0), b et p. None si alignés."""
    e = (b[0] ** 2 + b[1] ** 2) / 2.0
    f = (p[0] ** 2 + p[1] ** 2) / 2.0
    det = b[0] * p[1] - b[1] * p[0]
    scale = math.hypot(*b) * math.hypot(*p)
    if scale < 1e-12 or abs(det) < 1e-9 * scale:
        return None
    cx = (e * p[1] - b[1] * f) / det
    cy = (b[0] * f - e * p[0]) / det
    return cx, cy


# --------------------------------------------------------------------------
# Création des objets courbe
# --------------------------------------------------------------------------

def _link_object(context, name, curve_data):
    obj = bpy.data.objects.new(name, curve_data)
    context.view_layer.active_layer_collection.collection.objects.link(obj)
    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def _redraw_all_areas():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                area.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


def shape_output(context):
    """Type de résultat des formes 2D : 'MESH' (arêtes), 'FACE' (arêtes + face) ou 'CURVE'."""
    try:
        sc = context.scene
        if "wd_shapes_v2" not in sc.keys():        # scène jamais migrée (minuteur de démarrage manqué)
            if sc.dessin.sortie_formes == 'MESH':
                sc.dessin.sortie_formes = 'CURVE'
            sc["wd_shapes_v2"] = 1
            _redraw_all_areas()
        return context.scene.dessin.sortie_formes
    except AttributeError:
        return 'CURVE'


def build_shape_mesh(context, name, pts, closed, origin, mode, normal):
    """Contour en maillage : arêtes, plus une face si mode == 'FACE' et la forme est fermée. L'origine de l'objet = `origin`."""
    o = Vector(origin)
    verts = [tuple(Vector(q) - o) for q in pts]
    n = len(verts)
    edges = [(i, i + 1) for i in range(n - 1)]
    faces = []
    if closed and n > 2:
        edges.append((n - 1, 0))
        if mode == 'FACE':
            idx = list(range(n))
            nrm = Vector()
            for i in range(n):
                nrm += Vector(verts[i]).cross(Vector(verts[(i + 1) % n]))
            if nrm.dot(normal) < 0:
                idx.reverse()           # la face regarde du côté du plan de construction
            faces.append(idx)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, faces)
    me.update()
    obj = _link_object(context, name, me)
    obj.location = o
    return obj


def build_polyline(context, name, pts, closed):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for sp_pt, q in zip(sp.points, pts):
        sp_pt.co = (q.x, q.y, q.z, 1.0)
    sp.use_cyclic_u = closed
    return _link_object(context, name, cu)


def build_plane(context, name, corners, normal, origin):
    """Plan (maillage à une face) dont l'origine est le premier point cliqué."""
    o = origin
    me = bpy.data.meshes.new(name)
    verts = [tuple(c - o) for c in corners]
    face = [0, 1, 2, 3]
    if (corners[1] - corners[0]).cross(corners[2] - corners[1]).dot(normal) < 0:
        face.reverse()  # la face regarde du côté du plan de construction
    me.from_pydata(verts, [], [face])
    me.update()
    obj = _link_object(context, name, me)
    obj.location = o
    return obj


def edit_add_geometry(context, pts, edges, faces):
    """Ajoute sommets / arêtes / faces (coordonnées monde) au maillage en cours d'édition ; le nouveau est sélectionné."""
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        return None
    bm = bmesh.from_edit_mesh(obj.data)
    inv = obj.matrix_world.inverted()
    for v in bm.verts:
        v.select_set(False)
    new_v = [bm.verts.new(inv @ Vector(p)) for p in pts]
    created = list(new_v)
    for a, b in edges:
        try:
            created.append(bm.edges.new((new_v[a], new_v[b])))
        except ValueError:
            pass
    for f in faces:
        try:
            created.append(bm.faces.new([new_v[i] for i in f]))
        except ValueError:
            pass
    for g in created:
        g.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    return obj


def build_bezier_arc(context, name, c, u, v, r, t0, sweep, full):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    data = arc_bezier_data(c, u, v, r, t0, sweep)
    if full:
        first_left = data[-1][1]
        data = data[:-1]
        data[0] = (data[0][0], first_left, data[0][2])
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(data) - 1)
    for bp, (pos, hl, hr) in zip(sp.bezier_points, data):
        bp.handle_left_type = 'FREE'
        bp.handle_right_type = 'FREE'
        bp.co = pos
        bp.handle_left = hl
        bp.handle_right = hr
    sp.use_cyclic_u = full
    obj = _link_object(context, name, cu)
    obj["dessin_centre"] = (c.x, c.y, c.z)
    return obj


def addon_globals():
    """Tous les noms du paquet : les classes d'outils et d'opérateurs sont réparties dans ses modules."""
    import sys
    out = {}
    for name, mod in list(sys.modules.items()):
        if mod is not None and (name == __package__ or name.startswith(__package__ + ".")):
            out.update(vars(mod))
    return out


def _late_imports():
    pass
