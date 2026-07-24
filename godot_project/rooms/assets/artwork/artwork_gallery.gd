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

const LIVING_ROOM_ART: Array[Texture2D] = [
	preload("res://rooms/assets/artwork/gallery/living_dogs_and_puppies.jpg"),
	preload("res://rooms/assets/artwork/gallery/living_kittens_at_play.jpg"),
	preload("res://rooms/assets/artwork/gallery/living_cat_and_kittens.jpg"),
	preload("res://rooms/assets/artwork/gallery/living_three_puppies.jpg"),
]

const TV_ROOM_ART: Array[Texture2D] = [
	preload("res://rooms/assets/artwork/gallery/tv_cats_bachelor_party.jpg"),
	preload("res://rooms/assets/artwork/gallery/tv_wain_cat_faces.jpg"),
	preload("res://rooms/assets/artwork/gallery/tv_dogs_poker.jpg"),
	preload("res://rooms/assets/artwork/gallery/tv_animal_band.jpg"),
]


static func dorm_mural(room_index: int) -> Texture2D:
	return DORM_MURALS[posmod(room_index, DORM_MURALS.size())]
