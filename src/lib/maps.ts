type Coordinate = { lat: number; lng: number };

export function buildGoogleMapsLink(
  origin: Coordinate,
  destination: Coordinate,
  waypoint?: Coordinate | null,
) {
  const waypointParam = waypoint ? `&waypoints=${waypoint.lat},${waypoint.lng}` : "";
  return `https://www.google.com/maps/dir/?api=1&origin=${origin.lat},${origin.lng}&destination=${destination.lat},${destination.lng}${waypointParam}&travelmode=driving`;
}
