import threading
from typing import Optional
from enum import Enum

class VehicleType(Enum):
    CAR = 1
    TRUCK = 2

class ParkingLot:
    """Thread-safe parking lot with support for cars (1 spot) and trucks (2 adjacent spots)"""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.spots = [False] * capacity  # False = free, True = occupied
        self.lock = threading.RLock()  # Reentrant lock for thread safety
        
    def get_availability(self) -> dict:
        """Get current parking lot status"""
        with self.lock:
            return {
                'total': self.capacity,
                'occupied': sum(self.spots),
                'free': self.capacity - sum(self.spots),
                'spots': ['X' if spot else 'O' for spot in self.spots]
            }
    
    def _find_single_spot(self) -> Optional[int]:
        """Internal method to find a single free spot"""
        for i in range(self.capacity):
            if not self.spots[i]:
                return i
        return None
    
    def _find_adjacent_spots(self) -> Optional[int]:
        """Internal method to find 2 adjacent free spots"""
        for i in range(self.capacity - 1):
            if not self.spots[i] and not self.spots[i + 1]:
                return i
        return None
    
    def create_car(self):
        """Factory method to create a Car instance"""
        return Car(self)
    
    def create_truck(self):
        """Factory method to create a Truck instance"""
        return Truck(self)


class Vehicle:
    """Base class for vehicles"""
    
    def __init__(self, parking_lot: ParkingLot, vehicle_type: VehicleType):
        self.parking_lot = parking_lot
        self.vehicle_type = vehicle_type
        self.spot_index: Optional[int] = None
        
    def request_spot(self) -> Optional[int]:
        """Request a parking spot - to be implemented by subclasses"""
        raise NotImplementedError
        
    def yield_spot(self, idx: int) -> bool:
        """Yield a parking spot - to be implemented by subclasses"""
        raise NotImplementedError
        
    def __repr__(self):
        status = f"parked at {self.spot_index}" if self.spot_index is not None else "not parked"
        return f"{self.vehicle_type.name}({status})"


class Car(Vehicle):
    """Car class - requires 1 parking spot"""
    
    def __init__(self, parking_lot: ParkingLot):
        super().__init__(parking_lot, VehicleType.CAR)
    
    def request_spot(self) -> Optional[int]:
        """
        Request a single parking spot.
        Returns: spot index if successful, None if no spots available
        """
        with self.parking_lot.lock:
            # Check if already parked
            if self.spot_index is not None:
                print(f"Car already parked at spot {self.spot_index}")
                return None
            
            # Find free spot
            idx = self.parking_lot._find_single_spot()
            if idx is not None:
                self.parking_lot.spots[idx] = True
                self.spot_index = idx
                return idx
            
            return None  # No spot available
    
    def yield_spot(self, idx: int) -> bool:
        """
        Yield the parking spot.
        Args:
            idx: spot index to yield
        Returns: True if successful, False otherwise
        """
        with self.parking_lot.lock:
            # Validate the yield request
            if idx < 0 or idx >= self.parking_lot.capacity:
                print(f"Invalid spot index: {idx}")
                return False
            
            if self.spot_index is None:
                print("Car is not parked")
                return False
            
            if self.spot_index != idx:
                print(f"Car is parked at {self.spot_index}, not {idx}")
                return False
            
            # Release the spot
            self.parking_lot.spots[idx] = False
            self.spot_index = None
            return True


class Truck(Vehicle):
    """Truck class - requires 2 adjacent parking spots"""
    
    def __init__(self, parking_lot: ParkingLot):
        super().__init__(parking_lot, VehicleType.TRUCK)
    
    def request_spot(self) -> Optional[int]:
        """
        Request 2 adjacent parking spots.
        Returns: starting spot index if successful, None if no adjacent spots available
        """
        with self.parking_lot.lock:
            # Check if already parked
            if self.spot_index is not None:
                print(f"Truck already parked at spots {self.spot_index}-{self.spot_index + 1}")
                return None
            
            # Find adjacent spots
            idx = self.parking_lot._find_adjacent_spots()
            if idx is not None:
                self.parking_lot.spots[idx] = True
                self.parking_lot.spots[idx + 1] = True
                self.spot_index = idx
                return idx
            
            return None  # No adjacent spots available
    
    def yield_spot(self, idx: int) -> bool:
        """
        Yield the 2 parking spots.
        Args:
            idx: starting spot index to yield
        Returns: True if successful, False otherwise
        """
        with self.parking_lot.lock:
            # Validate the yield request
            if idx < 0 or idx >= self.parking_lot.capacity - 1:
                print(f"Invalid spot index: {idx}")
                return False
            
            if self.spot_index is None:
                print("Truck is not parked")
                return False
            
            if self.spot_index != idx:
                print(f"Truck is parked at {self.spot_index}, not {idx}")
                return False
            
            # Release both spots
            self.parking_lot.spots[idx] = False
            self.parking_lot.spots[idx + 1] = False
            self.spot_index = None
            return True


# ============================================================================
# DEMONSTRATION AND TESTING
# ============================================================================

def demonstrate_basic_usage():
    """Demonstrate basic parking lot operations"""
    print("=" * 60)
    print("BASIC USAGE DEMONSTRATION")
    print("=" * 60)
    
    # Create parking lot with 10 spots
    lot = ParkingLot(10)
    print(f"\nInitial state: {' '.join(lot.get_availability()['spots'])}")
    
    # Create and park a car
    car1 = lot.create_car()
    spot = car1.request_spot()
    print(f"\nCar1 requested spot: {spot}")
    print(f"State: {' '.join(lot.get_availability()['spots'])}")
    
    # Create and park a truck
    truck1 = lot.create_truck()
    spot = truck1.request_spot()
    print(f"\nTruck1 requested spot: {spot}")
    print(f"State: {' '.join(lot.get_availability()['spots'])}")
    
    # Park another car
    car2 = lot.create_car()
    spot = car2.request_spot()
    print(f"\nCar2 requested spot: {spot}")
    print(f"State: {' '.join(lot.get_availability()['spots'])}")
    
    # Car1 yields spot
    car1.yield_spot(car1.spot_index)
    print(f"\nCar1 yielded spot")
    print(f"State: {' '.join(lot.get_availability()['spots'])}")
    
    # Truck1 yields spots
    truck1.yield_spot(truck1.spot_index)
    print(f"\nTruck1 yielded spots")
    print(f"State: {' '.join(lot.get_availability()['spots'])}")
    
    print(f"\nFinal availability: {lot.get_availability()}")


def demonstrate_thread_safety():
    """Demonstrate thread-safe concurrent operations"""
    print("\n" + "=" * 60)
    print("THREAD SAFETY DEMONSTRATION")
    print("=" * 60)
    
    lot = ParkingLot(20)
    results = {'cars': [], 'trucks': []}
    lock = threading.Lock()
    
    def park_cars(num_cars: int):
        """Thread function to park multiple cars"""
        for i in range(num_cars):
            car = lot.create_car()
            spot = car.request_spot()
            with lock:
                results['cars'].append((i, spot))
            if spot is not None:
                # Simulate parking duration
                threading.Event().wait(0.001)
    
    def park_trucks(num_trucks: int):
        """Thread function to park multiple trucks"""
        for i in range(num_trucks):
            truck = lot.create_truck()
            spot = truck.request_spot()
            with lock:
                results['trucks'].append((i, spot))
            if spot is not None:
                # Simulate parking duration
                threading.Event().wait(0.001)
    
    # Create threads
    threads = []
    threads.append(threading.Thread(target=park_cars, args=(5,)))
    threads.append(threading.Thread(target=park_trucks, args=(3,)))
    threads.append(threading.Thread(target=park_cars, args=(5,)))
    
    # Start all threads
    for t in threads:
        t.start()
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    print(f"\nCars parked: {len([s for _, s in results['cars'] if s is not None])}/{len(results['cars'])}")
    print(f"Trucks parked: {len([s for _, s in results['trucks'] if s is not None])}/{len(results['trucks'])}")
    print(f"\nFinal state: {' '.join(lot.get_availability()['spots'])}")
    print(f"Availability: {lot.get_availability()}")


def demonstrate_edge_cases():
    """Demonstrate edge case handling"""
    print("\n" + "=" * 60)
    print("EDGE CASES DEMONSTRATION")
    print("=" * 60)
    
    lot = ParkingLot(5)
    
    print("\n1. Double parking attempt:")
    car = lot.create_car()
    spot1 = car.request_spot()
    print(f"   First request: {spot1}")
    spot2 = car.request_spot()
    print(f"   Second request: {spot2}")
    
    print("\n2. Invalid yield:")
    success = car.yield_spot(999)
    print(f"   Yield invalid spot: {success}")
    
    print("\n3. Full parking lot:")
    lot2 = ParkingLot(3)
    vehicles = []
    for i in range(5):
        car = lot2.create_car()
        spot = car.request_spot()
        vehicles.append(car)
        print(f"   Car {i+1} requested: {spot}")
    
    print("\n4. Truck requires adjacent spots:")
    lot3 = ParkingLot(5)
    # Park cars at positions 0, 2, 4
    car1 = lot3.create_car()
    car1.request_spot()
    car2 = lot3.create_car()
    car2.request_spot()
    car3 = lot3.create_car()
    car3.request_spot()
    
    print(f"   State: {' '.join(lot3.get_availability()['spots'])}")
    truck = lot3.create_truck()
    spot = truck.request_spot()
    print(f"   Truck request (needs 2 adjacent): {spot}")


if __name__ == "__main__":
    demonstrate_basic_usage()
    demonstrate_thread_safety()
    demonstrate_edge_cases()
