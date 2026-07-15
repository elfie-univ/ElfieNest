class_name ArtworkGallery
extends RefCounted

const DORM_MURALS: Array[Texture2D] = [
	preload("res://rooms/assets/artwork/gallery/monet_cliff_walk_pourville.jpg"),
	preload("res://rooms/assets/artwork/gallery/monet_stacks_wheat_summer.jpg"),
	preload("res://rooms/assets/artwork/gallery/inness_after_summer_shower.jpg"),
	preload("res://rooms/assets/artwork/gallery/seurat_sunday_grande_jatte.jpg"),
	preload("res://rooms/assets/artwork/gallery/vangogh_poets_garden.jpg"),
	preload("res://rooms/assets/artwork/gallery/renoir_seascape.jpg"),
	preload("res://rooms/assets/artwork/gallery/monet_impression_sunrise.jpg"),
	preload("res://rooms/assets/artwork/gallery/inness_home_of_heron.jpg"),
]


static func dorm_mural(room_index: int) -> Texture2D:
	return DORM_MURALS[posmod(room_index, DORM_MURALS.size())]
