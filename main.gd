extends Node3D

var server: UDPServer
var socket_port: int = 4242

@onready var skeleton: Skeleton3D = $"T-Pose/Skeleton3D"
var right_forearm_bone_id: int = -1

func _ready() -> void:
	server = UDPServer.new()
	var err = server.listen(socket_port)
	if err == OK:
		print("Listening for Python telemetry on port ", socket_port)
	else:
		print("Failed to bind UDP port!")

	if skeleton:
		right_forearm_bone_id = skeleton.find_bone("mixamorig_RightForeArm")
		if right_forearm_bone_id != -1:
			print("Found RightForeArm bone ID: ", right_forearm_bone_id)
		else:
			print("Warning: Could not find bone 'mixamorig_RightForeArm'!")

func _process(_delta: float) -> void:
	server.poll()
	if server.is_connection_available():
		var peer: PacketPeerUDP = server.take_connection()
		var raw_data = peer.get_packet().get_string_from_utf8()

		var json = JSON.new()
		if json.parse(raw_data) == OK:
			var data = json.data
			var angle: float = data.get("angle", 0.0)
			var is_valid: bool = data.get("tracking_valid", false)

			if is_valid and right_forearm_bone_id != -1:
				# Reset bone back to local rest pose
				skeleton.reset_bone_pose(right_forearm_bone_id)

				# Convert MediaPipe angle (40° to 180°) into proper elbow flex angle
				var bend_deg: float = 180.0 - angle
				var bend_rad: float = deg_to_rad(bend_deg)

				# Fetch base rest transform
				var rest_transform: Transform3D = skeleton.get_bone_rest(right_forearm_bone_id)

				# Invert bend_rad (-bend_rad) to flex UP toward the head instead of DOWN
				var new_basis: Basis = rest_transform.basis.rotated(Vector3.RIGHT, -bend_rad)

				# Apply updated rotation
				skeleton.set_bone_pose_rotation(right_forearm_bone_id, Quaternion(new_basis))
			elif right_forearm_bone_id != -1:
				# Reset to default posture when out of frame
				skeleton.reset_bone_pose(right_forearm_bone_id)