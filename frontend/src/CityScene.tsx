import { Canvas } from '@react-three/fiber'
import { Grid, Line, OrbitControls, PerspectiveCamera, Text } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'

const nodes: Record<string, [number, number]> = { Harbor: [-4, 0], Civic: [-2, -1], Market: [0, 0], North: [-3, -3], Central: [-1, -3], East: [1, -3], Hill: [-4, -5], Shelter: [-1, -5], Airport: [2, -5] }
const roads: [string, string][] = [['Harbor','Civic'],['Civic','Market'],['Harbor','North'],['Civic','North'],['Civic','Central'],['Market','Central'],['Market','East'],['North','Central'],['Central','East'],['North','Hill'],['North','Shelter'],['Central','Shelter'],['Central','Airport'],['East','Airport'],['Hill','Shelter'],['Shelter','Airport']]
const blocks: [number, number, number][] = [[-3.4,-.8,.44],[-1.3,-.7,.55],[.3,-1.5,.48],[-2.5,-2.3,.52],[-.5,-2.1,.7],[1.2,-2.1,.47],[-3.5,-4,.36],[-1.8,-4,.58],[.4,-4,.52],[2,-4,.38],[-3,-.1,.34],[-.3,.1,.44],[1.5,-.2,.46]]

function City({ route, closures, onIncident }: { route: string[]; closures: [string,string][]; onIncident: () => void }) {
  const routePoints = useMemo(() => route.map((name) => new THREE.Vector3(nodes[name][0], .13, nodes[name][1])), [route])
  return <>
    <color attach="background" args={['#09131e']} /><fog attach="fog" args={['#09131e', 15, 30]} />
    <ambientLight intensity={1.5} /><directionalLight position={[4,8,5]} intensity={2.2} color="#9ddaff" />
    <pointLight position={[-4,4,-1]} intensity={35} color="#00d6e9" distance={12} />
    <Grid position={[0,-.04,0]} args={[18,18]} cellSize={1} cellThickness={.5} cellColor="#1b394a" sectionSize={3} sectionColor="#1f5968" fadeDistance={17} infiniteGrid />
    {roads.map(([a,b]) => { const blocked=closures.some(([x,y]) => (x===a&&y===b)||(x===b&&y===a)); return <Line key={a+b} points={[[nodes[a][0],.04,nodes[a][1]],[nodes[b][0],.04,nodes[b][1]]]} color={blocked?'#ff5964':'#294554'} lineWidth={blocked?2:1.2} dashed={blocked} dashSize={.18} gapSize={.12} /> })}
    {blocks.map(([x,z,h],i) => <mesh key={i} position={[x,h/2,z]} castShadow><boxGeometry args={[.72,h,.72]} /><meshStandardMaterial color={i%3===0?'#17384a':'#122738'} emissive="#0e5164" emissiveIntensity={.24} metalness={.42} roughness={.48} /></mesh>)}
    {routePoints.length>1 && <Line points={routePoints} color="#00e5f4" lineWidth={4} />}
    <mesh position={[nodes.Harbor[0],.18,nodes.Harbor[1]]} onClick={onIncident}><sphereGeometry args={[.2,24,24]} /><meshStandardMaterial color="#ff6170" emissive="#ff3e64" emissiveIntensity={2.2} /></mesh>
    {Object.entries(nodes).map(([name,[x,z]]) => <group key={name} position={[x,.13,z]}><mesh><sphereGeometry args={[name==='Shelter'?.15:.07,16,16]} /><meshStandardMaterial color={name==='Shelter'?'#55efba':name==='Harbor'?'#ff6170':'#57d6ee'} emissive={name==='Shelter'?'#1ba77e':'#087b9b'} emissiveIntensity={1.2} /></mesh><Text position={[0,.36,0]} fontSize={.2} color="#b7cbd6" anchorX="center">{name}</Text></group>)}
    <mesh rotation={[-Math.PI/2,0,0]} position={[-3,-.01,.2]} onClick={onIncident}><circleGeometry args={[1.2,48]} /><meshBasicMaterial color="#258ac1" transparent opacity={.27} /></mesh>
  </>
}

export default function CityScene({ route, closures, onIncident }: { route: string[]; closures: [string,string][]; onIncident: () => void }) {
  return <Canvas dpr={[1,1.6]} gl={{ antialias:true, alpha:false }}><PerspectiveCamera makeDefault position={[7,9,11]} fov={45} /><OrbitControls enableDamping minDistance={6} maxDistance={21} maxPolarAngle={Math.PI/2.08} target={[-1,-.3,-2]} /><City route={route} closures={closures} onIncident={onIncident} /></Canvas>
}
